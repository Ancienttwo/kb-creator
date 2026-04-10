"""Validate and apply deterministic layout patches for source chapters."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result
from kb_creator.state import KBState, STATE_FILENAME


PATCH_OPERATIONS = (
    "replace_block",
    "wrap_code_block",
    "replace_with_table",
    "join_lines",
    "drop_noise_lines",
)


def _resolve_state_file(root: Path, explicit: Path | None) -> Path | None:
    if explicit:
        return explicit.resolve()
    candidate = root / STATE_FILENAME
    return candidate if candidate.exists() else None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_map(candidates_path: Path | None) -> dict[str, dict[str, Any]]:
    if not candidates_path or not candidates_path.exists():
        return {}
    payload = _load_json(candidates_path)
    return {item["candidate_id"]: item for item in payload.get("candidates", [])}


def _validate_patch(patch: dict[str, Any], candidates: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    candidate_id = patch.get("candidate_id")
    if not isinstance(candidate_id, str) or not candidate_id:
        errors.append("missing candidate_id")
    candidate = candidates.get(candidate_id, {})
    operation = patch.get("operation")
    if operation not in PATCH_OPERATIONS:
        errors.append(f"unsupported operation: {operation}")
    confidence = patch.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        errors.append("confidence must be a number between 0 and 1")
    payload = patch.get("payload")
    if not isinstance(payload, dict):
        errors.append("payload must be an object")
        payload = {}
    if candidate_id and candidate_id not in candidates:
        errors.append(f"candidate_id not found in candidates artifact: {candidate_id}")

    if operation == "replace_block" and not isinstance(payload.get("replacement"), str):
        errors.append("replace_block requires payload.replacement")
    if operation == "wrap_code_block" and not isinstance(payload.get("content"), str):
        errors.append("wrap_code_block requires payload.content")
    if operation == "replace_with_table":
        header = payload.get("header")
        rows = payload.get("rows")
        if not isinstance(header, list) or not header or not all(isinstance(cell, str) for cell in header):
            errors.append("replace_with_table requires payload.header string array")
        if not isinstance(rows, list) or not all(isinstance(row, list) for row in rows):
            errors.append("replace_with_table requires payload.rows array")
    if operation == "join_lines":
        separator = payload.get("separator", " ")
        replacement = payload.get("replacement")
        if not isinstance(separator, str):
            errors.append("join_lines payload.separator must be a string")
        if replacement is not None and not isinstance(replacement, str):
            errors.append("join_lines payload.replacement must be a string when present")
    if operation == "drop_noise_lines":
        lines = payload.get("lines", [])
        if not isinstance(lines, list) or not all(isinstance(item, str) for item in lines):
            errors.append("drop_noise_lines payload.lines must be a string array")

    if errors:
        return None, errors

    normalized = {
        "patch_id": patch.get("patch_id") or f"{candidate_id}:{operation}",
        "candidate_id": candidate_id,
        "chapter_path": candidate["chapter_path"],
        "operation": operation,
        "payload": payload,
        "rationale": patch.get("rationale", ""),
        "confidence": round(float(confidence), 2),
        "approved": bool(patch.get("approved", False)),
        "target_excerpt": candidate["source_excerpt"],
        "start_line": candidate.get("start_line"),
    }
    return normalized, []


def validate_patch_queue(
    queue_path: Path,
    *,
    candidates_path: Path | None = None,
) -> Result:
    """Validate a patch queue without mutating chapter files."""
    result = Result(ok=True, action="source_patch_validate", inputs={"queue_path": str(queue_path.resolve())})
    if not queue_path.exists():
        result.ok = False
        result.errors.append(f"patch queue not found: {queue_path}")
        return result

    queue = _load_json(queue_path)
    if not isinstance(queue, list):
        result.ok = False
        result.errors.append("patch queue must be a JSON array")
        return result

    candidates = _candidate_map(candidates_path)
    valid: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for patch in queue:
        normalized, errors = _validate_patch(patch, candidates)
        if errors:
            invalid.append({"patch": patch, "errors": errors})
            continue
        valid.append(normalized)

    result.ok = len(invalid) == 0
    result.outputs = {
        "valid_count": len(valid),
        "invalid_count": len(invalid),
        "valid_patches": valid,
        "invalid_patches": invalid,
    }
    return result


def _render_patch(normalized_patch: dict[str, Any]) -> str:
    operation = normalized_patch["operation"]
    payload = normalized_patch["payload"]
    if operation == "replace_block":
        return payload["replacement"].strip("\n")
    if operation == "wrap_code_block":
        language = payload.get("language", "text")
        content = payload["content"].strip("\n")
        return f"```{language}\n{content}\n```"
    if operation == "replace_with_table":
        header = payload["header"]
        rows = payload["rows"]
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
        ]
        for row in rows:
            cells = [str(cell) for cell in row[: len(header)]]
            while len(cells) < len(header):
                cells.append("")
            lines.append("| " + " | ".join(cells) + " |")
        return "\n".join(lines)
    if operation == "join_lines":
        replacement = payload.get("replacement")
        if isinstance(replacement, str):
            return replacement.strip("\n")
        separator = payload.get("separator", " ")
        source_lines = [line.strip() for line in normalized_patch["target_excerpt"].splitlines() if line.strip()]
        return separator.join(source_lines)
    if operation == "drop_noise_lines":
        to_drop = {line.strip() for line in payload.get("lines", [])}
        kept = []
        for line in normalized_patch["target_excerpt"].splitlines():
            stripped = line.strip()
            if stripped and stripped in to_drop:
                continue
            kept.append(line.rstrip())
        return "\n".join(line for line in kept if line.strip())
    raise ValueError(f"unsupported operation: {operation}")


def _find_block(lines: list[str], excerpt_lines: list[str], start_hint: int | None) -> int | None:
    if not excerpt_lines:
        return None
    candidates: list[int] = []
    if isinstance(start_hint, int):
        base = max(start_hint - 1, 0)
        for offset in range(-8, 9):
            probe = base + offset
            if probe < 0:
                continue
            candidates.append(probe)
    candidates.extend(range(0, len(lines) - len(excerpt_lines) + 1))
    seen: set[int] = set()
    for start in candidates:
        if start in seen or start < 0 or start + len(excerpt_lines) > len(lines):
            continue
        seen.add(start)
        if lines[start:start + len(excerpt_lines)] == excerpt_lines:
            return start
    return None


def _block_present(lines: list[str], block_lines: list[str]) -> bool:
    return _find_block(lines, block_lines, None) is not None


def apply_layout_patches(
    source_dir: Path,
    *,
    queue_path: Path | None = None,
    candidates_path: Path | None = None,
    overrides_path: Path | None = None,
    artifacts_dir: Path | None = None,
    state_path: Path | None = None,
    approve_all: bool = False,
    min_confidence: float | None = None,
) -> Result:
    """Merge approved queue items into overrides and apply them deterministically."""
    root = source_dir.resolve()
    result = Result(ok=True, action="source_patch_apply", inputs={"source_dir": str(root)})
    if not root.is_dir():
        result.ok = False
        result.errors.append(f"source directory not found: {root}")
        return result

    artifact_root = artifacts_dir.resolve() if artifacts_dir else root / ".kb-artifacts"
    queue_path = queue_path.resolve() if queue_path else None
    candidates_path = candidates_path.resolve() if candidates_path else (
        (artifact_root / "layout_candidates.json") if (artifact_root / "layout_candidates.json").exists() else None
    )
    overrides_path = overrides_path.resolve() if overrides_path else artifact_root / "layout_overrides.json"

    candidates = _candidate_map(candidates_path)
    selected: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    queue_total = 0

    if queue_path:
        if not queue_path.exists():
            result.ok = False
            result.errors.append(f"patch queue not found: {queue_path}")
            return result
        queue = _load_json(queue_path)
        if not isinstance(queue, list):
            result.ok = False
            result.errors.append("patch queue must be a JSON array")
            return result
        queue_total = len(queue)
        for patch in queue:
            normalized, errors = _validate_patch(patch, candidates)
            if errors:
                invalid.append({"patch": patch, "errors": errors})
                continue
            approved = approve_all or normalized["approved"]
            if min_confidence is not None and normalized["confidence"] >= min_confidence:
                approved = True
            if approved:
                selected.append(normalized)
    if invalid:
        result.ok = False
        result.errors.extend(
            f"{item['patch'].get('candidate_id', 'unknown')}: {'; '.join(item['errors'])}" for item in invalid
        )
        result.outputs["invalid_patches"] = invalid
        return result

    overrides: list[dict[str, Any]] = []
    if overrides_path.exists():
        existing = _load_json(overrides_path)
        if isinstance(existing, list):
            overrides = existing
    merged: dict[str, dict[str, Any]] = {item.get("patch_id", f"{item['candidate_id']}:{item['operation']}"): item for item in overrides}
    for item in selected:
        merged[item["patch_id"]] = item
    ordered_overrides = sorted(merged.values(), key=lambda item: item["patch_id"])
    overrides_path.parent.mkdir(parents=True, exist_ok=True)
    overrides_path.write_text(json.dumps(ordered_overrides, ensure_ascii=False, indent=2), encoding="utf-8")

    touched: dict[Path, list[dict[str, Any]]] = {}
    for patch in ordered_overrides:
        chapter_path = root / patch["chapter_path"]
        touched.setdefault(chapter_path, []).append(patch)

    applied = 0
    skipped = 0
    warnings: list[str] = []
    touched_paths: list[str] = []
    for chapter_path, chapter_patches in touched.items():
        if not chapter_path.exists():
            warnings.append(f"missing chapter for overrides: {chapter_path.relative_to(root).as_posix()}")
            continue
        lines = chapter_path.read_text(encoding="utf-8", errors="replace").splitlines()
        file_changed = False
        for patch in chapter_patches:
            excerpt_lines = patch["target_excerpt"].splitlines()
            replacement_lines = _render_patch(patch).splitlines()
            start = _find_block(lines, excerpt_lines, patch.get("start_line"))
            if start is None:
                if replacement_lines and _block_present(lines, replacement_lines):
                    skipped += 1
                    continue
                warnings.append(f"target excerpt not found for {patch['patch_id']}")
                continue
            end = start + len(excerpt_lines)
            if lines[start:end] == replacement_lines:
                skipped += 1
                continue
            lines[start:end] = replacement_lines
            applied += 1
            file_changed = True
        if file_changed:
            chapter_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            touched_paths.append(chapter_path.relative_to(root).as_posix())

    payload = {
        "source_dir": str(root),
        "queue_total": queue_total,
        "approved_from_queue": len(selected),
        "overrides_count": len(ordered_overrides),
        "applied_count": applied,
        "skipped_count": skipped,
        "touched_chapters": touched_paths,
        "warnings": warnings,
    }
    result.save_artifact("layout_overrides", ordered_overrides, artifact_root)
    result.save_artifact("layout_apply_report", payload, artifact_root)
    result.outputs = {
        "queue_total": queue_total,
        "approved_from_queue": len(selected),
        "overrides_count": len(ordered_overrides),
        "applied_count": applied,
        "skipped_count": skipped,
        "touched_chapters": touched_paths,
        "overrides_path": str(overrides_path),
        "report_path": result.artifacts["layout_apply_report"],
    }
    if warnings:
        result.warnings.extend(warnings)

    resolved_state = _resolve_state_file(root, state_path)
    if resolved_state:
        state = KBState.load(resolved_state)
        if state is not None:
            state.update_source_layer_status(
                split_complete=True,
                patches_pending=queue_total > len(selected),
                patches_applied=len(ordered_overrides) > 0,
                qa_verified=False,
            )
            state.save(resolved_state)

    return result
