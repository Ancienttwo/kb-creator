"""Document splitting engine with configurable boundary detection.

Splits large markdown files into chapter-level notes at detected boundaries.
Supports Chinese regulatory patterns, English technical headings, numbered
codes, and standard markdown heading levels.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result, log

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_MIN_LINES = 20
DEFAULT_MAX_LINES = 5000

DEFAULT_PATTERNS: list[dict[str, Any]] = [
    {"regex": r"^#{1,2}\s+第.+部",  "priority": 1, "type": "part"},
    {"regex": r"^#{1,2}\s+第.+章",  "priority": 2, "type": "chapter"},
    {"regex": r"^#{1,2}\s+附表",    "priority": 1, "type": "appendix"},
    {"regex": r"^#{1,2}\s+附錄",    "priority": 1, "type": "appendix"},
    {"regex": r"^#{1,3}\s+Chapter\s+\d+", "priority": 1, "type": "chapter"},
    {"regex": r"^#{1,3}\s+Section\s+\d+", "priority": 2, "type": "section"},
    {"regex": r"^#{1,3}\s+[A-Z]{2,}-\d{3}", "priority": 2, "type": "code"},
    {"regex": r"^#\s+",             "priority": 3, "type": "heading1"},
    {"regex": r"^##\s+",            "priority": 4, "type": "heading2"},
    {"regex": r"^###\s+",           "priority": 5, "type": "heading3"},
]

# Characters that are unsafe in filenames.
_UNSAFE_CHARS = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_filename(name: str) -> str:
    """Replace filesystem-unsafe characters and collapse whitespace."""
    name = _UNSAFE_CHARS.sub("_", name)
    name = re.sub(r"\s+", "-", name.strip())
    # Collapse repeated separators
    name = re.sub(r"[-_]{2,}", "-", name)
    return name or "untitled"


def _extract_title(line: str) -> str:
    """Strip leading markdown heading markers from a boundary line."""
    return re.sub(r"^#+\s*", "", line).strip()


def _build_frontmatter(meta: dict[str, Any]) -> str:
    """Build a YAML frontmatter block from a dict."""
    lines = ["---"]
    for key, value in meta.items():
        # Quote strings that could be mis-parsed by YAML
        if isinstance(value, str):
            safe = value.replace('"', '\\"')
            lines.append(f'{key}: "{safe}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Boundary detection
# ---------------------------------------------------------------------------


def detect_boundaries(content: str, patterns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Detect split boundaries in *content*.

    Parameters
    ----------
    content : str
        Full text of the markdown file.
    patterns : list[dict]
        Each entry has ``regex`` (str), ``priority`` (int), and ``type`` (str).

    Returns
    -------
    list[dict]
        Sorted list of ``{line, type, title, priority}`` dicts.  ``line`` is
        the 0-based line index where the boundary was found.
    """
    compiled: list[tuple[re.Pattern[str], int, str]] = []
    for pat in patterns:
        try:
            compiled.append((re.compile(pat["regex"]), pat.get("priority", 99), pat.get("type", "unknown")))
        except re.error as exc:
            log(f"skipping invalid regex {pat['regex']!r}: {exc}")

    lines = content.splitlines()
    boundaries: list[dict[str, Any]] = []
    seen_lines: set[int] = set()

    for rx, priority, btype in compiled:
        for idx, line in enumerate(lines):
            if idx in seen_lines:
                continue
            if rx.search(line):
                boundaries.append({
                    "line": idx,
                    "type": btype,
                    "title": _extract_title(line),
                    "priority": priority,
                })
                seen_lines.add(idx)

    # Stable sort: by line number, then by priority (lower = higher priority)
    boundaries.sort(key=lambda b: (b["line"], b["priority"]))
    return boundaries


# ---------------------------------------------------------------------------
# Single-file split
# ---------------------------------------------------------------------------


def split_file(
    input_path: Path,
    output_dir: Path,
    config: dict[str, Any],
    source_meta: dict[str, Any] | None = None,
) -> Result:
    """Split a single markdown file according to *config*.

    Parameters
    ----------
    input_path : Path
        Source markdown file.
    output_dir : Path
        Directory to write split notes into.
    config : dict
        Must contain ``patterns`` (list).  Optional keys: ``min_lines``,
        ``max_lines``.
    source_meta : dict | None
        Extra metadata to inject into each note's frontmatter.

    Returns
    -------
    Result
        ``outputs`` contains ``file_map`` (index -> path) and
        ``naming_map`` (index -> original title).
    """
    action = "split_file"
    result = Result(ok=True, action=action, inputs={"input": str(input_path), "output_dir": str(output_dir)})

    # --- Validate inputs ---------------------------------------------------
    if not input_path.exists():
        result.ok = False
        result.errors.append(f"input file not found: {input_path}")
        return result

    patterns = config.get("patterns", DEFAULT_PATTERNS)
    min_lines = config.get("min_lines", DEFAULT_MIN_LINES)
    max_lines = config.get("max_lines", DEFAULT_MAX_LINES)

    content = input_path.read_text(encoding="utf-8")
    all_lines = content.splitlines(keepends=True)
    total_lines = len(all_lines)

    log(f"splitting {input_path.name} ({total_lines} lines)")

    # --- Detect boundaries -------------------------------------------------
    boundaries = detect_boundaries(content, patterns)

    if not boundaries:
        result.warnings.append("no boundaries detected; file not split")
        result.outputs = {"file_map": {}, "naming_map": {}, "sections": 0}
        return result

    # --- Apply min_lines heuristic: absorb tiny sections -------------------
    filtered: list[dict[str, Any]] = []
    for i, b in enumerate(boundaries):
        if not filtered:
            filtered.append(b)
            continue
        gap = b["line"] - filtered[-1]["line"]
        if gap < min_lines:
            log(f"absorbing boundary at line {b['line']} ({b['title']!r}) into previous section ({gap} < {min_lines} lines)")
            result.warnings.append(f"absorbed small section '{b['title']}' ({gap} lines) into previous")
        else:
            filtered.append(b)

    boundaries = filtered

    # --- Build sections from boundaries ------------------------------------
    sections: list[dict[str, Any]] = []

    # Content before the first boundary (preamble)
    if boundaries[0]["line"] > 0:
        sections.append({
            "start": 0,
            "end": boundaries[0]["line"],
            "title": "preamble",
            "type": "preamble",
        })

    for i, b in enumerate(boundaries):
        end = boundaries[i + 1]["line"] if i + 1 < len(boundaries) else total_lines
        sections.append({
            "start": b["line"],
            "end": end,
            "title": b["title"],
            "type": b["type"],
        })

    # --- Warn on oversized sections ----------------------------------------
    for sec in sections:
        sec_lines = sec["end"] - sec["start"]
        if sec_lines > max_lines:
            result.warnings.append(
                f"section '{sec['title']}' has {sec_lines} lines (exceeds max_lines={max_lines})"
            )

    # --- Write output files ------------------------------------------------
    output_dir.mkdir(parents=True, exist_ok=True)
    file_map: dict[str, str] = {}
    naming_map: dict[str, str] = {}
    source_name = input_path.stem

    for idx, sec in enumerate(sections, start=1):
        seq = f"{idx:02d}"
        clean_title = _sanitize_filename(sec["title"])
        filename = f"{seq}-{clean_title}.md"
        out_path = output_dir / filename

        # Build frontmatter
        fm_data: dict[str, Any] = {
            "source_file": input_path.name,
            "chapter": sec["title"],
            "type": sec["type"],
        }
        if source_meta:
            fm_data["parent"] = source_meta.get("parent", source_name)
            fm_data.update({k: v for k, v in source_meta.items() if k != "parent"})
        else:
            fm_data["parent"] = source_name

        frontmatter = _build_frontmatter(fm_data)
        body = "".join(all_lines[sec["start"]:sec["end"]])

        out_path.write_text(frontmatter + body, encoding="utf-8")
        file_map[seq] = str(out_path)
        naming_map[seq] = sec["title"]
        log(f"  wrote {filename} (lines {sec['start']+1}-{sec['end']})")

    result.outputs = {
        "file_map": file_map,
        "naming_map": naming_map,
        "sections": len(sections),
        "total_lines": total_lines,
    }
    log(f"split into {len(sections)} sections")
    return result


# ---------------------------------------------------------------------------
# Batch split
# ---------------------------------------------------------------------------


def split_batch(
    manifest: list[dict[str, Any]] | Path,
    output_dir: Path,
    config: dict[str, Any],
    artifacts_dir: Path | None = None,
) -> Result:
    """Split multiple files described by *manifest*.

    Parameters
    ----------
    manifest : list[dict] | Path
        Either a list of ``{path: str, config?: dict}`` items, or a Path to a
        JSON file containing such a list.
    output_dir : Path
        Root output directory.  Each file's splits go into a subdirectory
        named after the source file's stem.
    config : dict
        Default split config; per-item overrides take precedence.
    artifacts_dir : Path | None
        If provided, intermediate results are persisted here.

    Returns
    -------
    Result
        Aggregated result with per-file outputs.
    """
    action = "split_batch"
    result = Result(ok=True, action=action)

    # --- Load manifest if it is a path -------------------------------------
    if isinstance(manifest, Path):
        if not manifest.exists():
            result.ok = False
            result.errors.append(f"manifest not found: {manifest}")
            return result
        try:
            manifest = json.loads(manifest.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            result.ok = False
            result.errors.append(f"failed to read manifest: {exc}")
            return result

    if not isinstance(manifest, list):
        result.ok = False
        result.errors.append("manifest must be a JSON array")
        return result

    result.inputs = {"manifest_count": len(manifest), "output_dir": str(output_dir)}

    per_file: dict[str, Any] = {}
    total_sections = 0
    ok_count = 0
    fail_count = 0

    for item in manifest:
        src_path = Path(item["path"])
        item_config = item.get("config", config)

        sub_dir = output_dir / src_path.stem
        sub_result = split_file(src_path, sub_dir, item_config, source_meta=item.get("meta"))

        per_file[str(src_path)] = {
            "ok": sub_result.ok,
            "sections": sub_result.outputs.get("sections", 0),
            "file_map": sub_result.outputs.get("file_map", {}),
            "warnings": sub_result.warnings,
            "errors": sub_result.errors,
        }

        if sub_result.ok:
            ok_count += 1
            total_sections += sub_result.outputs.get("sections", 0)
        else:
            fail_count += 1

        result.warnings.extend(sub_result.warnings)
        result.errors.extend(sub_result.errors)

    result.ok = fail_count == 0
    result.outputs = {
        "total_files": len(manifest),
        "ok": ok_count,
        "failed": fail_count,
        "total_sections": total_sections,
        "per_file": per_file,
    }

    if artifacts_dir:
        result.save_artifact("split_batch_result", result.outputs, artifacts_dir)

    if fail_count:
        log(f"batch split finished with {fail_count} failure(s)")
    else:
        log(f"batch split complete: {ok_count} files, {total_sections} sections")

    return result
