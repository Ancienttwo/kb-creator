"""Shared wiki helpers for KB repository operations."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract a shallow YAML frontmatter mapping from markdown text."""
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    data: dict[str, Any] = {}
    for line in content[3:end].strip().splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value.startswith("[") and value.endswith("]"):
            items = [item.strip().strip('"').strip("'") for item in value[1:-1].split(",") if item.strip()]
            data[key] = items
        else:
            data[key] = value
    return data


def extract_wikilinks(content: str) -> list[str]:
    return [match.group(1).split("|", 1)[0].split("#", 1)[0].strip() for match in re.finditer(r"\[\[([^\]]+)\]\]", content)]


def extract_headings(content: str, limit: int = 10) -> list[str]:
    headings: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                headings.append(heading)
        if len(headings) >= limit:
            break
    return headings


def summarize_markdown(content: str, max_chars: int = 240) -> str:
    """Extract a terse human-readable summary from markdown."""
    body: list[str] = []
    in_code = False
    for line in content.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("---") or stripped.startswith("|"):
            continue
        if stripped.startswith("> [!"):
            continue
        body.append(stripped.lstrip("> ").strip())
        if sum(len(part) for part in body) >= max_chars:
            break
    text = " ".join(part for part in body if part).strip()
    return text[:max_chars].strip()


def render_kb_schema() -> str:
    """Return the fixed KB schema guide document."""
    return "\n".join([
        "# KB Schema",
        "",
        "This repository is operated through the `kb-creator` Skill.",
        "The `kb` CLI is an internal deterministic runtime and never calls an LLM directly.",
        "",
        "## Skill Dependency",
        "",
        "- Writable wiki pages must follow the external `obsidian-markdown` Skill contract.",
        "- `kb-creator` owns KB lifecycle, provenance, state, and artifact placement.",
        "- `obsidian-markdown` owns Obsidian syntax correctness for wikilinks, frontmatter, callouts, embeds, and note-writing conventions.",
        "",
        "## Page Types",
        "",
        "- `summary`: one source-oriented page derived from a raw markdown source.",
        "- `concept`: synthesized concept hub that links related summaries.",
        "- `index`: navigational overview or catalog page.",
        "- `query-note`: reusable filed-back answer version generated from wiki pages.",
        "- `query-history`: an index page in `wiki/queries/` that points to the latest query-note version.",
        "- `health-report`: structural integrity report.",
        "",
        "## Frontmatter Conventions",
        "",
        "- Every wiki page should declare `type`.",
        "- Summary pages should include `source_path`, `source_key`, and `source_hash`.",
        "- Concept pages should include `concept_key`, `aliases`, and `source_count`.",
        "- Query note versions should include `question`, `sources`, `derived_from_query_output`, `version`, and `version_group`.",
        "- Query history indexes should declare `type: index` and `index_kind: query-history`.",
        "",
        "## Obsidian Syntax Contract",
        "",
        "- Use `[[wikilinks]]` for internal KB page references and markdown links only for external URLs.",
        "- Use valid YAML frontmatter at the top of writable wiki pages.",
        "- Query history and query note version pages must follow the naming conventions below.",
        "- If a page fails these syntax rules, treat it as an `obsidian-markdown` contract violation and repair it through the Skill layer, not by free-form drift.",
        "",
        "## Workflow",
        "",
        "1. `kb ingest` normalizes source files into `raw/sources/`.",
        "2. `kb compile --emit-workset` updates deterministic wiki pages and emits a machine-readable workset for higher-level agents.",
        "3. Before any wiki-writing phase, verify the external `obsidian-markdown` Skill is available.",
        "4. `kb health` checks structural integrity; `kb lint` surfaces KB-maintenance candidates, including Obsidian contract violations.",
        "5. `kb query --mode scaffold|synthesize` creates reusable answer artifacts; `--file-back yes` writes query history/index artifacts into `wiki/queries/`.",
        "",
        "## Naming Rules",
        "",
        "- Keep raw sources immutable after ingest.",
        "- Use lowercase slugged filenames for concept pages.",
        "- Query history indexes live at `wiki/queries/<slug>.md`; immutable versions live at `wiki/queries/<slug>--vN.md`.",
        "- Append chronological events to `wiki/log.md`; do not rewrite history there.",
        "",
        "## File-Back Policy",
        "",
        "- Only file back answers that are grounded in existing wiki pages.",
        "- Filed-back query notes must point to their source pages and source output artifact.",
        "- Repeat file-back of the same question should merge into the latest version only when the grounded answer body is unchanged; otherwise create a new version.",
        "- KB maintenance agents may update existing pages, but should prefer explicit workset- or lint-driven edits over unconstrained rewrites.",
        "- Do not emit free-form wiki page mutations unless the `obsidian-markdown` dependency Skill is active.",
        "",
    ]) + "\n"


def parse_log_entries(log_path: Path) -> list[dict[str, Any]]:
    """Parse append-only wiki log entries."""
    if not log_path.exists():
        return []
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("## ["):
            if current is not None:
                entries.append(current)
            match = re.match(r"## \[(.+?)\] ([^|]+)\| (.+)", line)
            if match:
                current = {
                    "timestamp": match.group(1).strip(),
                    "operation": match.group(2).strip(),
                    "title": match.group(3).strip(),
                    "body": [],
                }
            else:
                current = {"timestamp": "", "operation": "", "title": line[3:].strip(), "body": []}
        elif current is not None:
            current["body"].append(line)
    if current is not None:
        entries.append(current)
    return entries


def append_log_entry(
    log_path: Path,
    operation: str,
    title: str,
    touched_sources: list[str],
    touched_pages: list[str],
    warnings: list[str] | None = None,
    next_questions: list[str] | None = None,
) -> str:
    """Append one standardized KB log entry."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    header = f"## [{timestamp}] {operation} | {title}"
    lines = [header, ""]
    if touched_sources:
        lines.append(f"- Touched sources: {', '.join(touched_sources)}")
    if touched_pages:
        lines.append(f"- Touched pages: {', '.join(touched_pages)}")
    if warnings:
        lines.append(f"- Warnings: {'; '.join(warnings)}")
    if next_questions:
        lines.append(f"- Next questions: {'; '.join(next_questions)}")
    lines.append("")
    existing = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else "# KB Log\n\n"
    if not existing.endswith("\n"):
        existing += "\n"
    log_path.write_text(existing + "\n".join(lines), encoding="utf-8")
    return header


def refresh_wiki_index(kb_root: Path, wiki_dir: Path, schema_path: Path | None = None) -> Path:
    """Rebuild the wiki home index from current wiki pages."""
    notes: list[dict[str, str]] = []
    for md_file in sorted(wiki_dir.rglob("*.md")):
        rel_path = md_file.relative_to(wiki_dir).as_posix()
        if rel_path == "index.md":
            continue
        content = md_file.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        summary = summarize_markdown(content, max_chars=180) or "_No summary available._"
        title = frontmatter.get("title") or md_file.stem
        section = rel_path.split("/", 1)[0]
        notes.append({
            "section": section,
            "title": str(title),
            "path": rel_path,
            "summary": summary,
        })

    grouped: dict[str, list[dict[str, str]]] = {}
    for note in notes:
        grouped.setdefault(note["section"], []).append(note)

    lines = [
        "---",
        'type: "index"',
        'index_kind: "homepage"',
        "---",
        "",
        "# Knowledge Base",
        "",
        f"- Total wiki pages: {len(notes)}",
        f"- Generated: {datetime.now(timezone.utc).isoformat()}",
    ]
    if schema_path is not None:
        lines.append(f"- Schema: [{schema_path.name}](../{schema_path.name})")
    lines.extend([
        "- [[indexes/all-sources|All Sources]]",
        "- [[indexes/all-concepts|All Concepts]]",
        "- [[log|KB Log]]",
        "",
    ])
    for section in sorted(grouped):
        lines.append(f"## {section}")
        lines.append("")
        for note in grouped[section]:
            lines.append(f"- [[{Path(note['path']).with_suffix('').as_posix()}|{note['title']}]] - {note['summary']}")
        lines.append("")

    index_path = wiki_dir / "index.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path
