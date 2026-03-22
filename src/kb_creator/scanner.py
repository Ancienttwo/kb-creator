"""Source directory scanner and analyzer.

Recursively scans a directory for supported document files, reports
statistics, detects language bias, identifies filename grouping patterns,
and flags large files that may need splitting.

Output conforms to the Result contract from contracts.py.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result, log

# ── constants ────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS: set[str] = {
    ".pdf", ".docx", ".pptx", ".xlsx",
    ".csv", ".html", ".txt", ".md",
}

LARGE_FILE_THRESHOLD: int = 50 * 1024  # 50 KB

# Directories to skip during scanning (toolchain / caches / vault internals)
IGNORE_DIRS: set[str] = {
    ".venv", "venv", ".git", "node_modules", "__pycache__", ".tox",
    ".mypy_cache", ".pytest_cache", ".kb-artifacts", ".obsidian",
    ".cache", "dist", "build", ".egg-info",
}

# CJK Unicode ranges for language detection
_CJK_RANGES = (
    ("\u4e00", "\u9fff"),   # CJK Unified Ideographs
    ("\u3400", "\u4dbf"),   # CJK Unified Ideographs Extension A
)


# ── helpers ──────────────────────────────────────────────────────────

def _is_cjk_char(ch: str) -> bool:
    """Return True if *ch* falls inside a CJK Unicode range."""
    for lo, hi in _CJK_RANGES:
        if lo <= ch <= hi:
            return True
    return False


def _detect_language(filenames: list[str]) -> str:
    """Detect dominant language bias from filenames.

    Samples the first 1 KB worth of filename characters and checks the
    ratio of CJK characters.  Returns ``"cjk"``, ``"latin"``, or
    ``"mixed"``.
    """
    if not filenames:
        return "unknown"

    sample = ""
    for name in filenames:
        sample += name
        if len(sample) >= 1024:
            break

    sample = sample[:1024]

    cjk_count = sum(1 for ch in sample if _is_cjk_char(ch))
    alpha_count = sum(1 for ch in sample if ch.isalpha())

    if alpha_count == 0:
        return "unknown"

    ratio = cjk_count / alpha_count
    if ratio > 0.5:
        return "cjk"
    elif ratio > 0.1:
        return "mixed"
    return "latin"


def _detect_groups(filenames: list[str]) -> list[dict[str, Any]]:
    """Identify filename patterns that suggest natural groupings.

    Looks for:
    - Numbered patterns like GL-001, LD-002
    - Common prefixes shared by 2+ files
    - Directory-based groupings (handled separately in scan())
    """
    groups: list[dict[str, Any]] = []

    # ── numbered patterns (PREFIX-NNN) ───────────────────────────────
    pattern = re.compile(r"^([A-Za-z]+)[_\-](\d+)")
    prefix_counter: Counter[str] = Counter()
    prefix_examples: dict[str, list[str]] = defaultdict(list)

    for name in filenames:
        m = pattern.match(name)
        if m:
            prefix = m.group(1).upper()
            prefix_counter[prefix] += 1
            if len(prefix_examples[prefix]) < 3:
                prefix_examples[prefix].append(name)

    for prefix, count in prefix_counter.items():
        if count >= 2:
            groups.append({
                "type": "numbered_pattern",
                "pattern": f"{prefix}-NNN",
                "count": count,
                "examples": prefix_examples[prefix],
            })

    # ── common prefixes (first word before space / underscore) ───────
    word_pattern = re.compile(r"^([^\s_\-\.]{2,})")
    word_counter: Counter[str] = Counter()
    word_examples: dict[str, list[str]] = defaultdict(list)

    for name in filenames:
        stem = Path(name).stem
        m = word_pattern.match(stem)
        if m:
            word = m.group(1)
            # skip single-char or already captured as numbered pattern
            if word.upper() not in prefix_counter or prefix_counter[word.upper()] < 2:
                word_counter[word] += 1
                if len(word_examples[word]) < 3:
                    word_examples[word].append(name)

    for word, count in word_counter.items():
        if count >= 3:
            groups.append({
                "type": "common_prefix",
                "prefix": word,
                "count": count,
                "examples": word_examples[word],
            })

    return groups


# ── main entry point ─────────────────────────────────────────────────

def scan(source_dir: Path, artifacts_dir: Path | None = None) -> Result:
    """Scan *source_dir* for supported files and return a Result.

    Parameters
    ----------
    source_dir:
        Root directory to scan recursively.
    artifacts_dir:
        Optional directory for persisting the detailed file manifest.
    """
    result = Result(
        ok=True,
        action="scan",
        inputs={"source_dir": str(source_dir)},
    )

    if not source_dir.is_dir():
        result.ok = False
        result.errors.append(f"source_dir does not exist or is not a directory: {source_dir}")
        return result

    log(f"Scanning {source_dir} ...")

    # ── walk ─────────────────────────────────────────────────────────
    format_counts: Counter[str] = Counter()
    format_sizes: Counter[str] = Counter()
    large_files: list[dict[str, Any]] = []
    dir_groups: Counter[str] = Counter()
    all_filenames: list[str] = []
    file_manifest: list[dict[str, Any]] = []
    total_size: int = 0
    skipped: int = 0

    for dirpath, dirnames, filenames in os.walk(source_dir):
        # Prune toolchain and hidden directories in-place
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        rel_dir = os.path.relpath(dirpath, source_dir)

        for fname in filenames:
            ext = Path(fname).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                skipped += 1
                continue

            filepath = Path(dirpath) / fname
            try:
                size = filepath.stat().st_size
            except OSError as exc:
                result.warnings.append(f"Cannot stat {filepath}: {exc}")
                continue

            format_counts[ext] += 1
            format_sizes[ext] += size
            total_size += size
            all_filenames.append(fname)
            dir_groups[rel_dir] += 1

            entry: dict[str, Any] = {
                "path": str(filepath.relative_to(source_dir)),
                "format": ext,
                "size": size,
            }
            file_manifest.append(entry)

            if size > LARGE_FILE_THRESHOLD:
                large_files.append({
                    "path": str(filepath.relative_to(source_dir)),
                    "size": size,
                    "size_human": _human_size(size),
                })

    total_files = sum(format_counts.values())
    log(f"Found {total_files} supported files ({skipped} skipped)")

    # ── language detection ───────────────────────────────────────────
    language = _detect_language(all_filenames)

    # ── grouping suggestions ─────────────────────────────────────────
    filename_groups = _detect_groups(all_filenames)

    # directory-based groups (only dirs with 2+ files)
    directory_groups = [
        {"directory": d, "count": c}
        for d, c in dir_groups.most_common()
        if c >= 2 and d != "."
    ]

    # ── assemble outputs ─────────────────────────────────────────────
    result.outputs = {
        "total_files": total_files,
        "total_size": total_size,
        "total_size_human": _human_size(total_size),
        "skipped_files": skipped,
        "format_counts": dict(format_counts.most_common()),
        "format_sizes": {k: v for k, v in format_sizes.most_common()},
        "language": language,
        "large_files": large_files,
        "grouping_suggestions": {
            "filename_patterns": filename_groups,
            "directory_groups": directory_groups,
        },
    }

    if not total_files:
        result.warnings.append("No supported files found in source directory.")

    # ── optional artifact ────────────────────────────────────────────
    if artifacts_dir is not None and file_manifest:
        result.save_artifact("scan_report", file_manifest, artifacts_dir)
        log(f"Report saved to {result.artifacts['scan_report']}")

    return result


def _human_size(nbytes: int) -> str:
    """Return a human-readable size string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}" if unit != "B" else f"{nbytes} B"
        nbytes /= 1024  # type: ignore[assignment]
    return f"{nbytes:.1f} TB"
