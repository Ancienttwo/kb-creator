"""Vault registry generator.

Scans all notes in a vault or KB repository and produces a structured JSON
index (`vault_registry.json`) for agent retrieval and navigation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result, log
from kb_creator.wiki_ops import (
    extract_headings,
    extract_wikilinks,
    parse_frontmatter,
    parse_log_entries,
    summarize_markdown,
)


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
    page_sources: dict[str, list[str]] = {}
    source_pages: dict[str, list[str]] = {}

    for md_file in sorted(note_root.rglob("*.md")):
        rel_path = str(md_file.relative_to(note_root))
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            result.warnings.append(f"Could not read: {rel_path}")
            continue

        fm = parse_frontmatter(content)
        headings = extract_headings(content)
        line_count = content.count("\n") + 1
        page_summary = summarize_markdown(content, max_chars=220)

        entry: dict[str, Any] = {
            "title": str(fm.get("title", md_file.stem)),
            "path": rel_path,
            "line_count": line_count,
            "headings": headings,
            "outbound_links": [],
            "inbound_links": 0,
            "summary": page_summary,
        }

        for field in ("source_file", "format", "category", "parent", "type", "status", "tags", "chapter", "source_path", "question"):
            if field in fm:
                entry[field] = fm[field]
                indexed_fields.add(field)

        outbound = extract_wikilinks(content)
        entry["outbound_links"] = outbound
        for target in outbound:
            inbound_counts[Path(target).name] = inbound_counts.get(Path(target).name, 0) + 1

        sources: list[str] = []
        source_path = fm.get("source_path")
        if isinstance(source_path, str) and source_path:
            sources.append(source_path)
        fm_sources = fm.get("sources")
        if isinstance(fm_sources, list):
            sources.extend(str(item) for item in fm_sources if item)
        if isinstance(fm_sources, str) and fm_sources:
            sources.append(fm_sources)
        page_sources[rel_path] = sorted(set(sources))
        for source in page_sources[rel_path]:
            source_pages.setdefault(source, []).append(rel_path)

        note_entries.append(entry)

    for entry in note_entries:
        entry["inbound_links"] = inbound_counts.get(Path(entry["path"]).stem, 0)

    log(f"Indexed {len(note_entries)} notes with fields: {sorted(indexed_fields)}")

    result.outputs = {
        "total_notes": len(note_entries),
        "indexed_fields": sorted(indexed_fields),
    }

    registry: dict[str, Any] = {
        "version": 3,
        "generated": datetime.now(timezone.utc).isoformat(),
        "notes": note_entries,
        "page_sources": page_sources,
        "source_pages": source_pages,
        "query_outputs": [],
        "log_entries": [],
        "stats": {
            "total_notes": len(note_entries),
            "total_categories": len({entry.get("category") for entry in note_entries if entry.get("category")}),
            "total_outputs": 0,
            "total_sources": 0,
            "total_log_entries": 0,
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
        query_outputs = []
        if outputs_root.is_dir():
            for path in sorted(outputs_root.rglob("*.md")):
                output_artifacts.append({
                    "path": path.relative_to(kb_root).as_posix(),
                    "kind": path.parent.name,
                })
                if path.parent.name == "qa":
                    content = path.read_text(encoding="utf-8", errors="replace")
                    fm = parse_frontmatter(content)
                    query_outputs.append({
                        "path": path.relative_to(kb_root).as_posix(),
                        "question": fm.get("question", ""),
                        "mode": fm.get("mode", ""),
                        "sources": fm.get("sources", []),
                    })
        registry["sources"] = raw_sources
        registry["outputs"] = output_artifacts
        registry["query_outputs"] = query_outputs
        registry["log_entries"] = parse_log_entries(kb_root / "wiki" / "log.md")
        registry["stats"]["total_sources"] = len(raw_sources)
        registry["stats"]["total_outputs"] = len(output_artifacts)
        registry["stats"]["total_log_entries"] = len(registry["log_entries"])
        result.outputs["total_sources"] = len(raw_sources)
        result.outputs["total_outputs"] = len(output_artifacts)

    target_dir = artifacts_dir or vault_dir / ".kb-artifacts"
    result.save_artifact("vault_registry", registry, target_dir)

    return result
