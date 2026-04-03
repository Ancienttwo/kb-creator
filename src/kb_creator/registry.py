"""Vault registry generator.

Scans all notes in a vault or KB repository and produces a structured JSON
index (`vault_registry.json`) for agent retrieval and navigation.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
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


def _extract_wikilinks(content: str) -> list[str]:
    """Extract wikilink targets from note content."""
    return [match.group(1).split("|", 1)[0].split("#", 1)[0].strip() for match in re.finditer(r"\[\[([^\]]+)\]\]", content)]


def build_registry(vault_dir: Path, artifacts_dir: Path | None = None) -> Result:
    """Build a registry for a vault or KB repository."""
    result = Result(ok=True, action="registry", inputs={"vault_dir": str(vault_dir)})

    if not vault_dir.is_dir():
        return Result(ok=False, action="registry", errors=[f"Not a directory: {vault_dir}"])

    kb_root = vault_dir if (vault_dir / "wiki").is_dir() else None
    note_root = vault_dir / "wiki" if kb_root else vault_dir

    note_entries: list[dict[str, Any]] = []
    indexed_fields = set()
    inbound_counts: dict[str, int] = {}
    stem_to_path: dict[str, str] = {}

    for md_file in sorted(note_root.rglob("*.md")):
        rel_path = str(md_file.relative_to(note_root))
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
            "outbound_links": [],
            "inbound_links": 0,
        }
        stem_to_path[md_file.stem] = rel_path

        # Copy frontmatter fields
        for field in ("source_file", "format", "category", "parent", "type", "status", "tags", "chapter"):
            if field in fm:
                entry[field] = fm[field]
                indexed_fields.add(field)

        if tldr:
            entry["summary"] = tldr
            indexed_fields.add("summary")

        outbound = _extract_wikilinks(content)
        entry["outbound_links"] = outbound
        for target in outbound:
            inbound_counts[Path(target).name] = inbound_counts.get(Path(target).name, 0) + 1

        note_entries.append(entry)

    for entry in note_entries:
        entry["inbound_links"] = inbound_counts.get(Path(entry["path"]).stem, 0)

    log(f"Indexed {len(note_entries)} notes with fields: {sorted(indexed_fields)}")

    result.outputs = {
        "total_notes": len(note_entries),
        "indexed_fields": sorted(indexed_fields),
    }

    registry: dict[str, Any] = {
        "version": 2,
        "generated": datetime.now(timezone.utc).isoformat(),
        "notes": note_entries,
        "stats": {
            "total_notes": len(note_entries),
            "total_categories": len({entry.get("category") for entry in note_entries if entry.get("category")}),
            "total_outputs": 0,
            "total_sources": 0,
        },
    }

    if kb_root is not None:
        raw_sources_root = kb_root / "raw" / "sources"
        outputs_root = kb_root / "outputs"
        raw_sources = []
        if raw_sources_root.is_dir():
            raw_sources = [
                {
                    "path": path.relative_to(kb_root).as_posix(),
                    "hash": "",
                }
                for path in sorted(raw_sources_root.rglob("*.md"))
            ]
        output_artifacts = []
        if outputs_root.is_dir():
            for path in sorted(outputs_root.rglob("*.md")):
                output_artifacts.append({
                    "path": path.relative_to(kb_root).as_posix(),
                    "kind": path.parent.name,
                })
        registry["sources"] = raw_sources
        registry["outputs"] = output_artifacts
        registry["stats"]["total_sources"] = len(raw_sources)
        registry["stats"]["total_outputs"] = len(output_artifacts)
        result.outputs["total_sources"] = len(raw_sources)
        result.outputs["total_outputs"] = len(output_artifacts)

    target_dir = artifacts_dir or vault_dir / ".kb-artifacts"
    result.save_artifact("vault_registry", registry, target_dir)

    return result
