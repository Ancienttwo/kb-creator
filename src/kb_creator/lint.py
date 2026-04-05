"""Knowledge-base maintenance lint checks."""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result
from kb_creator.kb import KBLayout, _load_state
from kb_creator.wiki_ops import (
    append_log_entry,
    parse_frontmatter,
    parse_log_entries,
    refresh_wiki_index,
    summarize_markdown,
)


def _load_workset(layout: KBLayout) -> list[dict[str, Any]]:
    artifact = layout.artifacts_dir / "compile_workset.json"
    if not artifact.exists():
        return []
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    return payload.get("sources", [])


def run_lint_checks(kb_root: Path) -> Result:
    """Emit KB-maintenance candidates without mutating wiki pages."""
    layout = KBLayout(kb_root.resolve())
    state = _load_state(layout)
    result = Result(ok=True, action="kb_lint", inputs={"kb_root": str(layout.root)})

    summaries: list[dict[str, Any]] = []
    stale_pages: list[dict[str, str]] = []
    concept_frequency: Counter[str] = Counter()
    source_to_pages: dict[str, list[str]] = {}
    obsidian_contract_violations: list[dict[str, str]] = []

    for note_path in sorted(layout.wiki_dir.rglob("*.md")):
        rel_path = note_path.relative_to(layout.root).as_posix()
        content = note_path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        if not frontmatter.get("type"):
            obsidian_contract_violations.append({
                "page": rel_path,
                "reason": "missing required `type` frontmatter for a writable KB page",
            })
        if content.count("[[") != content.count("]]"):
            obsidian_contract_violations.append({
                "page": rel_path,
                "reason": "unbalanced wikilink delimiters; page should be repaired via obsidian-markdown contract rules",
            })
        for label, target in re.findall(r"\[([^\]]+)\]\(([^)]+)\)", content):
            if target.endswith(".md") and "://" not in target:
                obsidian_contract_violations.append({
                    "page": rel_path,
                    "reason": f"uses markdown link `{label}` -> `{target}` for an internal markdown target; use wikilinks instead",
                })
        if rel_path.startswith("wiki/queries/"):
            name = note_path.name
            page_type = str(frontmatter.get("type", ""))
            index_kind = str(frontmatter.get("index_kind", ""))
            if "--v" in name:
                required = ("question", "sources", "derived_from_query_output", "version", "version_group")
                missing = [field for field in required if field not in frontmatter]
                if page_type != "query-note" or missing:
                    obsidian_contract_violations.append({
                        "page": rel_path,
                        "reason": f"query-note version page must declare type=query-note and fields {', '.join(required)}; missing {', '.join(missing) if missing else 'none'}",
                    })
            else:
                if page_type != "index" or index_kind != "query-history":
                    obsidian_contract_violations.append({
                        "page": rel_path,
                        "reason": "query history index must declare `type: index` and `index_kind: query-history`",
                    })
        if frontmatter.get("type") == "summary":
            summary_item = {
                "path": rel_path,
                "source_path": frontmatter.get("source_path", ""),
                "source_hash": frontmatter.get("source_hash", ""),
                "summary": summarize_markdown(content, max_chars=220),
                "headings": frontmatter.get("headings", []),
            }
            summaries.append(summary_item)
            if summary_item["source_path"]:
                source_to_pages.setdefault(summary_item["source_path"], []).append(rel_path)
                raw_path = layout.root / summary_item["source_path"]
                if raw_path.exists():
                    raw_hash = state.files.get(frontmatter.get("source_key", ""), {}).get("hash", "")
                    if raw_hash and raw_hash != summary_item["source_hash"]:
                        stale_pages.append({
                            "page": rel_path,
                            "source_path": summary_item["source_path"],
                            "reason": "summary source hash does not match current source hash",
                        })
            for heading in frontmatter.get("headings", []):
                if isinstance(heading, str) and heading:
                    concept_frequency[heading] += 1

    existing_concepts = {path.stem for path in layout.wiki_concepts_dir.glob("*.md")}
    missing_concept_pages = [
        {"concept": concept, "frequency": count}
        for concept, count in concept_frequency.most_common()
        if count >= 2 and concept.casefold().replace(" ", "-") not in existing_concepts
    ]

    conflict_candidates: list[dict[str, Any]] = []
    grouped_by_source_count: dict[int, list[str]] = {}
    for concept_path in sorted(layout.wiki_concepts_dir.glob("*.md")):
        content = concept_path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        source_count = int(frontmatter.get("source_count", "0") or 0)
        grouped_by_source_count.setdefault(source_count, []).append(concept_path.relative_to(layout.root).as_posix())
    for count, pages in grouped_by_source_count.items():
        if count >= 2:
            conflict_candidates.append({
                "group": f"concept-pages-with-{count}-sources",
                "pages": pages,
                "reason": "multi-source concepts should be reviewed for synthesis quality and contradiction handling",
            })

    cold_pages: list[dict[str, str]] = []
    recent_pages = set(state.last_query_sources)
    if state.last_filed_query:
        recent_pages.add(state.last_filed_query)
    for note_path in sorted(layout.wiki_dir.rglob("*.md")):
        rel_path = note_path.relative_to(layout.root).as_posix()
        if rel_path in recent_pages:
            continue
        if rel_path.startswith("wiki/indexes/") or rel_path == "wiki/index.md" or rel_path == "wiki/log.md":
            continue
        if note_path.stat().st_mtime < (datetime.now(timezone.utc).timestamp() - 60):
            cold_pages.append({
                "page": rel_path,
                "reason": "page was not part of the most recent compile/query context",
            })

    workset = _load_workset(layout)
    research_questions: list[str] = []
    if missing_concept_pages:
        research_questions.extend(
            f"Should the KB promote '{item['concept']}' into a dedicated concept page?" for item in missing_concept_pages[:3]
        )
    if conflict_candidates:
        research_questions.append("Which multi-source concept pages need explicit contradiction notes or confidence qualifiers?")
    if obsidian_contract_violations:
        research_questions.append("Which Obsidian contract violations should be repaired first through the external obsidian-markdown Skill?")
    if workset:
        research_questions.extend(
            f"Does {item['summary_page']} require manual synthesis with {len(item['existing_pages_to_review'])} related pages?"
            for item in workset[:2]
        )

    report = {
        "missing_concept_pages": missing_concept_pages,
        "stale_pages": stale_pages,
        "conflict_candidates": conflict_candidates,
        "obsidian_contract_violations": obsidian_contract_violations,
        "cold_pages": cold_pages[:25],
        "research_questions": research_questions,
        "log_entries": parse_log_entries(layout.wiki_log_path)[-5:],
    }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    md_path = layout.outputs_health_dir / f"lint-{stamp}.md"
    lines = [
        "---",
        'type: "health-report"',
        f'generated_at: "{datetime.now(timezone.utc).isoformat()}"',
        'report_kind: "lint"',
        "---",
        "",
        "# KB Lint Report",
        "",
        f"- Missing concept pages: {len(missing_concept_pages)}",
        f"- Stale pages: {len(stale_pages)}",
        f"- Conflict candidates: {len(conflict_candidates)}",
        f"- Obsidian contract violations: {len(obsidian_contract_violations)}",
        f"- Cold pages: {len(cold_pages[:25])}",
        f"- Research questions: {len(research_questions)}",
        "",
    ]
    for key, value in report.items():
        lines.append(f"## {key}")
        lines.append("")
        if not value:
            lines.append("- none")
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
                else:
                    lines.append(f"- {item}")
        lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    result.save_artifact("lint_report", report, layout.artifacts_dir)
    refresh_wiki_index(layout.root, layout.wiki_dir, schema_path=layout.kb_schema_path)
    state.last_log_entry = append_log_entry(
        layout.wiki_log_path,
        "lint",
        f"Generated KB lint report with {len(research_questions)} research questions",
        touched_sources=sorted(source_to_pages)[:10],
        touched_pages=[md_path.relative_to(layout.root).as_posix()],
        next_questions=research_questions[:3],
    )
    state.phase = "lint"
    state.save(layout.root)

    result.outputs = {
        "report_path": str(md_path),
        "counts": {
            "missing_concept_pages": len(missing_concept_pages),
            "stale_pages": len(stale_pages),
            "conflict_candidates": len(conflict_candidates),
            "obsidian_contract_violations": len(obsidian_contract_violations),
            "cold_pages": len(cold_pages[:25]),
            "research_questions": len(research_questions),
        },
    }
    return result
