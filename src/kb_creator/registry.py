"""Vault registry generator.

Scans all notes in a vault and produces a structured JSON index
(vault_registry.json) for agent retrieval and navigation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result, log


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    fm_text = content[3:end].strip()
    result: dict[str, Any] = {}
    for line in fm_text.split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip("\"'")
            if value.startswith("[") and value.endswith("]"):
                value = [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
            result[key] = value
    return result


def _extract_tldr(content: str) -> str:
    """Extract TLDR callout text from note content."""
    match = re.search(r"> \[!tldr\]\s*\n((?:>.*\n)*)", content, re.IGNORECASE)
    if not match:
        return ""
    lines = match.group(1).strip().split("\n")
    return " ".join(line.lstrip("> ").strip() for line in lines if line.strip())


def _extract_headings(content: str) -> list[str]:
    """Extract top-level headings from content."""
    headings: list[str] = []
    for line in content.split("\n"):
        if line.startswith("# ") or line.startswith("## "):
            heading = line.lstrip("#").strip()
            if heading:
                headings.append(heading)
    return headings[:10]  # Cap at 10


def build_registry(vault_dir: Path, artifacts_dir: Path | None = None) -> Result:
    """Build a vault registry indexing all notes.

    The registry maps each note's relative path to its metadata,
    enabling fast lookups by category, tag, parent, or keyword.
    """
    result = Result(ok=True, action="registry", inputs={"vault_dir": str(vault_dir)})

    if not vault_dir.is_dir():
        return Result(ok=False, action="registry", errors=[f"Not a directory: {vault_dir}"])

    registry: dict[str, dict[str, Any]] = {}
    indexed_fields = set()

    for md_file in sorted(vault_dir.rglob("*.md")):
        rel_path = str(md_file.relative_to(vault_dir))
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            result.warnings.append(f"Could not read: {rel_path}")
            continue

        fm = _parse_frontmatter(content)
        tldr = _extract_tldr(content)
        headings = _extract_headings(content)
        line_count = content.count("\n") + 1

        entry: dict[str, Any] = {
            "title": md_file.stem,
            "path": rel_path,
            "line_count": line_count,
            "headings": headings,
        }

        # Copy frontmatter fields
        for field in ("source_file", "format", "category", "parent", "type", "status", "tags", "chapter"):
            if field in fm:
                entry[field] = fm[field]
                indexed_fields.add(field)

        if tldr:
            entry["summary"] = tldr
            indexed_fields.add("summary")

        registry[rel_path] = entry

    log(f"Indexed {len(registry)} notes with fields: {sorted(indexed_fields)}")

    result.outputs = {
        "total_notes": len(registry),
        "indexed_fields": sorted(indexed_fields),
    }

    target_dir = artifacts_dir or vault_dir / ".kb-artifacts"
    result.save_artifact("vault_registry", registry, target_dir)

    return result
