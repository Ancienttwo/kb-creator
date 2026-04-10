"""Detect high-risk source-layout fragments before AI-assisted repair."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from kb_creator.contracts import Result
from kb_creator.state import KBState, STATE_FILENAME


RISK_TYPES = (
    "table_fragment",
    "chart_block",
    "short_column_relation",
    "heading_break",
    "list_fragment",
    "running_header_noise",
)

_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
_NOISE_RE = re.compile(r"^\s*(?:\d+|Page\s+\d+|第\s*\d+\s*页|[-_=]{2,}|[·•])\s*$")
_LIST_RE = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)、]\s+|[一二三四五六七八九十]+[、.)])")
_TABLE_SPLIT_RE = re.compile(r"\s{2,}|\t+")
_RELATION_TERMS = {"刑", "冲", "破", "害", "合", "克", "生"}
_CHART_TERMS = {
    "子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥",
    "甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸",
    "贵", "后", "阴", "玄", "常", "虎", "空", "龙", "勾", "合", "朱", "蛇",
}


def _iter_markdown_files(root: Path) -> Iterable[Path]:
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        yield path


def _resolve_state_file(root: Path, explicit: Path | None) -> Path | None:
    if explicit:
        return explicit.resolve()
    candidate = root / STATE_FILENAME
    return candidate if candidate.exists() else None


def _normalize_excerpt(text: str) -> str:
    lines = [" ".join(line.strip().split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)


def _block_text(lines: list[str], start: int, end: int) -> str:
    return "\n".join(lines[start:end]).strip("\n")


def _context(lines: list[str], start: int, end: int, radius: int = 2) -> tuple[list[str], list[str]]:
    before = [line for line in lines[max(0, start - radius):start] if line.strip()]
    after = [line for line in lines[end:min(len(lines), end + radius)] if line.strip()]
    return before, after


def _page_hint(lines: list[str], start: int) -> str | None:
    for idx in range(start, max(-1, start - 8), -1):
        if idx < 0:
            break
        stripped = lines[idx].strip()
        if re.fullmatch(r"(?:第\s*)?\d+(?:\s*页)?", stripped):
            return stripped
    return None


def _find_heading(lines: list[str], start: int) -> str:
    for idx in range(start, -1, -1):
        stripped = lines[idx].strip()
        if _HEADING_RE.match(stripped):
            return stripped.lstrip("#").strip()
    return ""


def _make_candidate(
    root: Path,
    path: Path,
    lines: list[str],
    start: int,
    end: int,
    risk_type: str,
    confidence: float,
) -> dict[str, Any]:
    excerpt = _block_text(lines, start, end)
    before, after = _context(lines, start, end)
    return {
        "candidate_id": f"{path.relative_to(root).as_posix()}:{start + 1}-{end}:{risk_type}",
        "chapter_path": path.relative_to(root).as_posix(),
        "page_hint": _page_hint(lines, start),
        "heading": _find_heading(lines, start),
        "risk_type": risk_type,
        "source_excerpt": excerpt,
        "normalized_excerpt": _normalize_excerpt(excerpt),
        "confidence": round(confidence, 2),
        "start_line": start + 1,
        "end_line": end,
        "context_before": before,
        "context_after": after,
    }


def _scan_table_fragments(root: Path, path: Path, lines: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped or _HEADING_RE.match(stripped):
            idx += 1
            continue
        block_start = idx
        token_counts: list[int] = []
        block_end = idx
        while block_end < len(lines):
            current = lines[block_end].rstrip()
            if not current.strip() or _HEADING_RE.match(current):
                break
            cells = [cell.strip() for cell in _TABLE_SPLIT_RE.split(current.strip()) if cell.strip()]
            if len(cells) < 3:
                break
            if any(len(cell) > 12 for cell in cells):
                break
            token_counts.append(len(cells))
            block_end += 1
        if block_end - block_start >= 3 and len(set(token_counts)) == 1:
            candidates.append(_make_candidate(root, path, lines, block_start, block_end, "table_fragment", 0.9))
            idx = block_end
            continue
        idx += 1
    return candidates


def _scan_chart_blocks(root: Path, path: Path, lines: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    idx = 0
    while idx < len(lines):
        if not lines[idx].strip() or _HEADING_RE.match(lines[idx]):
            idx += 1
            continue
        block_end = idx
        hits = 0
        while block_end < len(lines):
            current = lines[block_end].strip()
            if not current or _HEADING_RE.match(current):
                break
            tokens = current.split()
            if len(current) > 24 or len(tokens) > 8:
                break
            if sum(1 for token in tokens if token in _CHART_TERMS) >= max(2, len(tokens) // 2):
                hits += 1
                block_end += 1
                continue
            break
        if block_end - idx >= 4 and hits >= 4:
            candidates.append(_make_candidate(root, path, lines, idx, block_end, "chart_block", 0.86))
            idx = block_end
            continue
        idx += 1
    return candidates


def _scan_short_column_relations(root: Path, path: Path, lines: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    idx = 0
    while idx < len(lines):
        if not lines[idx].strip() or _HEADING_RE.match(lines[idx]):
            idx += 1
            continue
        block_end = idx
        short_lines = 0
        relation_hits = 0
        while block_end < len(lines):
            current = lines[block_end].strip()
            if not current or _HEADING_RE.match(current):
                break
            if len(current) > 8 or _LIST_RE.match(current):
                break
            short_lines += 1
            if any(term in current for term in _RELATION_TERMS):
                relation_hits += 1
            block_end += 1
        if short_lines >= 4 and relation_hits >= 2:
            candidates.append(_make_candidate(root, path, lines, idx, block_end, "short_column_relation", 0.82))
            idx = block_end
            continue
        idx += 1
    return candidates


def _scan_heading_breaks(root: Path, path: Path, lines: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        if not _HEADING_RE.match(line.strip()):
            continue
        short_lines = 0
        end = idx + 1
        for probe in range(idx + 1, min(len(lines), idx + 6)):
            current = lines[probe].strip()
            if not current:
                continue
            end = probe + 1
            if len(current) <= 4 and not _LIST_RE.match(current):
                short_lines += 1
                continue
            if len(current) > 12:
                break
        if short_lines >= 3:
            candidates.append(_make_candidate(root, path, lines, idx, end, "heading_break", 0.71))
    return candidates


def _scan_list_fragments(root: Path, path: Path, lines: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    idx = 0
    while idx < len(lines):
        current = lines[idx].strip()
        if not _LIST_RE.match(current):
            idx += 1
            continue
        block_end = idx + 1
        fragmented = 0
        while block_end < len(lines):
            probe = lines[block_end].strip()
            if not probe or _HEADING_RE.match(probe):
                break
            if len(probe) <= 4:
                fragmented += 1
                block_end += 1
                continue
            if _LIST_RE.match(probe):
                block_end += 1
                continue
            break
        if fragmented >= 2:
            candidates.append(_make_candidate(root, path, lines, idx, block_end, "list_fragment", 0.68))
            idx = block_end
            continue
        idx += 1
    return candidates


def _scan_running_header_noise(root: Path, path: Path, lines: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not _NOISE_RE.match(stripped):
            continue
        if idx == 0:
            continue
        prev_non_empty = next((lines[probe].strip() for probe in range(idx - 1, -1, -1) if lines[probe].strip()), "")
        if _HEADING_RE.match(prev_non_empty):
            candidates.append(_make_candidate(root, path, lines, idx, idx + 1, "running_header_noise", 0.75))
    return candidates


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: (-item["confidence"], item["chapter_path"], item["start_line"])):
        key = (candidate["chapter_path"], candidate["risk_type"], candidate["normalized_excerpt"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return sorted(deduped, key=lambda item: (-item["confidence"], item["chapter_path"], item["start_line"]))


def run_layout_qa(
    source_dir: Path,
    *,
    artifacts_dir: Path | None = None,
    state_path: Path | None = None,
) -> Result:
    """Analyze markdown chapters and emit layout-risk candidates."""
    root = source_dir.resolve()
    result = Result(ok=True, action="source_layout_qa", inputs={"source_dir": str(root)})

    if not root.is_dir():
        result.ok = False
        result.errors.append(f"source directory not found: {root}")
        return result

    candidates: list[dict[str, Any]] = []
    for path in _iter_markdown_files(root):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        candidates.extend(_scan_table_fragments(root, path, lines))
        candidates.extend(_scan_chart_blocks(root, path, lines))
        candidates.extend(_scan_short_column_relations(root, path, lines))
        candidates.extend(_scan_heading_breaks(root, path, lines))
        candidates.extend(_scan_list_fragments(root, path, lines))
        candidates.extend(_scan_running_header_noise(root, path, lines))

    deduped = _dedupe_candidates(candidates)
    by_risk: dict[str, int] = {}
    by_chapter: dict[str, int] = {}
    for candidate in deduped:
        by_risk[candidate["risk_type"]] = by_risk.get(candidate["risk_type"], 0) + 1
        by_chapter[candidate["chapter_path"]] = by_chapter.get(candidate["chapter_path"], 0) + 1

    payload = {
        "source_dir": str(root),
        "candidate_count": len(deduped),
        "risk_counts": by_risk,
        "chapter_counts": by_chapter,
        "candidates": deduped,
    }

    artifact_root = artifacts_dir.resolve() if artifacts_dir else root / ".kb-artifacts"
    result.save_artifact("layout_candidates", payload, artifact_root)
    result.outputs = {
        "candidate_count": len(deduped),
        "risk_counts": by_risk,
        "chapter_counts": by_chapter,
        "top_candidates": deduped[:10],
        "artifact_path": result.artifacts["layout_candidates"],
    }

    resolved_state = _resolve_state_file(root, state_path)
    if resolved_state:
        state = KBState.load(resolved_state)
        if state is not None:
            state.update_source_layer_status(
                split_complete=True,
                layout_qa_complete=True,
                patches_pending=len(deduped) > 0,
                qa_verified=len(deduped) == 0,
            )
            state.save(resolved_state)

    return result
