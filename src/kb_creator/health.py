"""Health checks for compiled KB repositories."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result
from kb_creator.kb import KBLayout, _load_state


def _parse_frontmatter(content: str) -> dict[str, str]:
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    data: dict[str, str] = {}
    for line in content[3:end].strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            data[key.strip()] = value.strip().strip('"')
    return data


def _wikilinks(content: str) -> list[str]:
    return [match.group(1).split("|", 1)[0].split("#", 1)[0].strip() for match in re.finditer(r"\[\[([^\]]+)\]\]", content)]


def run_health_checks(kb_root: Path) -> Result:
    """Run KB integrity checks and write a markdown report."""
    layout = KBLayout(kb_root.resolve())
    state = _load_state(layout)
    result = Result(ok=True, action="kb_health", inputs={"kb_root": str(layout.root)})

    note_index: dict[str, dict[str, Any]] = {}
    inbound: dict[str, set[str]] = {}
    broken_links: list[dict[str, str]] = []
    missing_metadata: list[str] = []
    weak_links: list[str] = []
    valid_targets = {path.stem for path in layout.root.rglob("*.md")}

    for note_path in sorted(layout.wiki_dir.rglob("*.md")):
        rel_path = note_path.relative_to(layout.root).as_posix()
        stem = note_path.stem
        content = note_path.read_text(encoding="utf-8", errors="replace")
        fm = _parse_frontmatter(content)
        links = _wikilinks(content)
        note_index[stem] = {
            "path": rel_path,
            "frontmatter": fm,
            "outbound": links,
        }
        for key in ("type",):
            if key not in fm:
                missing_metadata.append(rel_path)
                break

    stems = set(note_index)
    for stem, entry in note_index.items():
        for target in entry["outbound"]:
            target_stem = Path(target).name
            if target_stem in stems:
                inbound.setdefault(target_stem, set()).add(stem)
            elif target_stem not in valid_targets:
                broken_links.append({"from": entry["path"], "target": target})

    orphaned = [
        entry["path"]
        for stem, entry in note_index.items()
        if entry["frontmatter"].get("type") != "index"
        and not inbound.get(stem)
        and not entry["outbound"]
    ]

    for stem, entry in note_index.items():
        if entry["frontmatter"].get("type") == "index":
            continue
        degree = len(inbound.get(stem, set())) + len(entry["outbound"])
        if degree < 2:
            weak_links.append(entry["path"])

    duplicate_concepts: dict[str, list[str]] = {}
    for entry in note_index.values():
        if entry["frontmatter"].get("type") != "concept":
            continue
        key = entry["frontmatter"].get("concept_key", entry["path"]).casefold()
        duplicate_concepts.setdefault(key, []).append(entry["path"])
    duplicate_concepts = {k: v for k, v in duplicate_concepts.items() if len(v) > 1}

    summary_gaps: list[str] = []
    source_coverage_gaps: list[str] = []
    for raw_path in sorted(layout.raw_sources_dir.rglob("*.md")):
        raw_rel = raw_path.relative_to(layout.root).as_posix()
        matches = [entry["path"] for entry in note_index.values() if entry["frontmatter"].get("source_path") == raw_rel]
        if not matches:
            summary_gaps.append(raw_rel)
        source_key = next((key for key, meta in state.files.items() if meta.get("raw_path") == raw_rel), raw_rel)
        artifacts = state.files.get(source_key, {}).get("artifacts", [])
        if not artifacts:
            source_coverage_gaps.append(raw_rel)

    stale_indexes: list[str] = []
    note_mtime = max((path.stat().st_mtime for path in layout.wiki_dir.rglob("*.md")), default=0)
    for index_path in sorted(layout.wiki_indexes_dir.glob("*.md")):
        if index_path.stat().st_mtime < note_mtime:
            stale_indexes.append(index_path.relative_to(layout.root).as_posix())

    report = {
        "missing_metadata": missing_metadata,
        "orphaned_notes": orphaned,
        "broken_links": broken_links,
        "weak_link_structure": weak_links,
        "duplicate_concepts": duplicate_concepts,
        "stale_indexes": stale_indexes,
        "summary_gaps": summary_gaps,
        "source_coverage_gaps": source_coverage_gaps,
    }

    layout.outputs_health_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    md_path = layout.outputs_health_dir / f"health-{stamp}.md"
    md_lines = [
        "---",
        'type: "health-report"',
        f'generated_at: "{datetime.now(timezone.utc).isoformat()}"',
        "---",
        "",
        "# KB Health Report",
        "",
        f"- Missing metadata: {len(missing_metadata)}",
        f"- Orphaned notes: {len(orphaned)}",
        f"- Broken links: {len(broken_links)}",
        f"- Weak-link notes: {len(weak_links)}",
        f"- Duplicate concepts: {len(duplicate_concepts)}",
        f"- Stale indexes: {len(stale_indexes)}",
        f"- Summary gaps: {len(summary_gaps)}",
        f"- Source coverage gaps: {len(source_coverage_gaps)}",
        "",
        "## Details",
        "",
    ]
    for key, value in report.items():
        md_lines.append(f"### {key}")
        if not value:
            md_lines.append("- none")
        elif isinstance(value, dict):
            for group, items in value.items():
                md_lines.append(f"- {group}: {', '.join(items)}")
        else:
            for item in value:
                md_lines.append(f"- {item}")
        md_lines.append("")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")

    result.outputs = {
        "report_path": str(md_path),
        "counts": {
            "missing_metadata": len(missing_metadata),
            "orphaned_notes": len(orphaned),
            "broken_links": len(broken_links),
            "weak_link_structure": len(weak_links),
            "duplicate_concepts": len(duplicate_concepts),
            "stale_indexes": len(stale_indexes),
            "summary_gaps": len(summary_gaps),
            "source_coverage_gaps": len(source_coverage_gaps),
        },
    }
    result.save_artifact("health_report", report, layout.artifacts_dir)

    state.last_health_report = str(md_path.relative_to(layout.root))
    state.phase = "health"
    state.save(layout.root)
    return result
