"""Query materialization for KB repositories."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result
from kb_creator.kb import KBLayout, _load_state
from kb_creator.wiki_ops import (
    append_log_entry,
    extract_headings,
    parse_frontmatter,
    refresh_wiki_index,
    summarize_markdown,
)


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w\u3400-\u9fff]+", text.lower()) if len(token) >= 2]


def _markdown_body(markdown: str) -> str:
    if markdown.startswith("---"):
        end = markdown.find("\n---\n", 3)
        if end != -1:
            return markdown[end + 5:].strip()
    return markdown.strip()


def _query_slug(question: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^\w\u3400-\u9fff]+", "-", question.lower())).strip("-") or "query"


def _content_hash(question: str, selected: list[dict[str, Any]], rendered_output: str) -> str:
    payload = {
        "question": question,
        "sources": [entry["path"] for entry in selected],
        "body": _markdown_body(rendered_output),
    }
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if isinstance(value, str) and value:
        return [value]
    return []


def _query_versions(layout: KBLayout, slug: str) -> list[dict[str, Any]]:
    versions: list[dict[str, Any]] = []
    for note_path in sorted(layout.wiki_queries_dir.glob(f"{slug}--v*.md")):
        content = note_path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        try:
            version = int(frontmatter.get("version", "0") or 0)
        except ValueError:
            version = 0
        versions.append({
            "path": note_path,
            "rel_path": note_path.relative_to(layout.root).as_posix(),
            "version": version,
            "content_hash": str(frontmatter.get("content_hash", "")),
            "outputs": _normalize_list(frontmatter.get("derived_from_query_outputs")),
            "question": str(frontmatter.get("question", "")),
        })
    versions.sort(key=lambda item: (item["version"], item["rel_path"]))
    return versions


def _write_query_version(
    note_path: Path,
    question: str,
    selected: list[dict[str, Any]],
    rendered_output: str,
    output_paths: list[str],
    version: int,
    slug: str,
    previous_version: str,
    content_hash: str,
) -> None:
    sources_field = ", ".join(f'"{entry["path"]}"' for entry in selected)
    outputs_field = ", ".join(f'"{path}"' for path in output_paths)
    question_yaml = question.replace('"', '\\"')
    body = _markdown_body(rendered_output)
    lines = [
        "---",
        'type: "query-note"',
        f'question: "{question_yaml}"',
        f"sources: [{sources_field}]",
        f'derived_from_query_output: "{output_paths[-1]}"',
        f"derived_from_query_outputs: [{outputs_field}]",
        f"version: {version}",
        f'version_group: "{slug}"',
        f'previous_version: "{previous_version}"',
        f'content_hash: "{content_hash}"',
        "---",
        "",
        body,
        "",
    ]
    note_path.write_text("\n".join(lines), encoding="utf-8")


def _write_query_history_index(
    layout: KBLayout,
    question: str,
    slug: str,
    versions: list[dict[str, Any]],
) -> Path:
    index_path = layout.wiki_queries_dir / f"{slug}.md"
    latest = versions[-1]
    question_yaml = question.replace('"', '\\"')
    version_paths = ", ".join(f'"{item["rel_path"]}"' for item in versions)
    lines = [
        "---",
        'type: "index"',
        'index_kind: "query-history"',
        f'question: "{question_yaml}"',
        f'latest_version: "{latest["rel_path"]}"',
        f"versions: [{version_paths}]",
        "---",
        "",
        f"# {question}",
        "",
        "## Latest Version",
        "",
        f'- [[{Path(latest["rel_path"]).with_suffix("").relative_to("wiki").as_posix()}|Version {latest["version"]}]]',
        "",
        "## Version History",
        "",
    ]
    for item in reversed(versions):
        lines.append(
            f'- [[{Path(item["rel_path"]).with_suffix("").relative_to("wiki").as_posix()}|Version {item["version"]}]] '
            f'({len(item["outputs"])} linked outputs)'
        )
    lines.append("")
    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path


def _load_registry_hints(layout: KBLayout) -> dict[str, dict[str, Any]]:
    artifact = layout.artifacts_dir / "vault_registry.json"
    if not artifact.exists():
        return {}
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    hints: dict[str, dict[str, Any]] = {}
    for note in payload.get("notes", []):
        path = note.get("path")
        if path:
            hints[f"wiki/{path}"] = note
    return hints


def _load_workset_hints(layout: KBLayout) -> set[str]:
    artifact = layout.artifacts_dir / "compile_workset.json"
    if not artifact.exists():
        return set()
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    pages: set[str] = set()
    for item in payload.get("sources", []):
        pages.add(item.get("summary_page", ""))
        for page in item.get("candidate_concept_pages", []):
            pages.add(page)
        for page in item.get("existing_pages_to_review", []):
            pages.add(page)
    return {page for page in pages if page}


def _score_notes(layout: KBLayout, question: str) -> list[dict[str, Any]]:
    tokens = set(_tokenize(question))
    registry_hints = _load_registry_hints(layout)
    workset_pages = _load_workset_hints(layout)
    index_content = (layout.wiki_dir / "index.md").read_text(encoding="utf-8", errors="replace") if (layout.wiki_dir / "index.md").exists() else ""

    note_entries: list[dict[str, Any]] = []
    for note_path in sorted(layout.wiki_dir.rglob("*.md")):
        content = note_path.read_text(encoding="utf-8", errors="replace")
        rel_path = note_path.relative_to(layout.root).as_posix()
        rel_wiki_path = note_path.relative_to(layout.wiki_dir).as_posix()
        frontmatter = parse_frontmatter(content)
        if rel_path in {"wiki/index.md", "wiki/log.md"}:
            continue
        if frontmatter.get("type") == "query-note":
            continue
        if frontmatter.get("type") == "index" and frontmatter.get("index_kind") == "query-history":
            continue
        haystack = content.lower()
        score = sum(haystack.count(token) for token in tokens)
        if rel_path in workset_pages:
            score += 2
        if rel_path in registry_hints:
            registry_entry = registry_hints[rel_path]
            score += sum(1 for token in tokens if token in json.dumps(registry_entry, ensure_ascii=False).lower())
        if rel_wiki_path != "index.md" and rel_wiki_path.replace(".md", "") in index_content:
            score += 1
        if score <= 0:
            continue
        preview = summarize_markdown(content, max_chars=320)
        note_entries.append({
            "path": rel_path,
            "score": score,
            "preview": preview,
            "title": frontmatter.get("title", note_path.stem),
            "source_path": frontmatter.get("source_path", ""),
            "category": frontmatter.get("category", ""),
            "headings": extract_headings(content, limit=5),
        })

    note_entries.sort(key=lambda item: (-item["score"], item["path"]))
    return note_entries


def _render_scaffold(question: str, timestamp: datetime, selected: list[dict[str, Any]]) -> str:
    sources_field = ", ".join(f'"{entry["path"]}"' for entry in selected)
    question_yaml = question.replace('"', '\\"')
    lines = [
        "---",
        f'mode: "scaffold"',
        f'question: "{question_yaml}"',
        f'asked_at: "{timestamp.date().isoformat()}"',
        f"sources: [{sources_field}]",
        'type: "qa-output"',
        "---",
        "",
        f"# {question}",
        "",
        "## Answer Draft",
        "",
    ]
    if selected:
        lines.append("This query matched the following knowledge artifacts. Use them as grounded context for a downstream LLM answer or manual synthesis.")
    else:
        lines.append("No matching wiki notes were found for this query.")
    lines.extend(["", "## Sources", ""])
    for entry in selected:
        lines.append(f"- [[{Path(entry['path']).with_suffix('').as_posix()}]] (score: {entry['score']})")
        if entry["preview"]:
            lines.append(f"  - {entry['preview']}")
    lines.append("")
    return "\n".join(lines)


def _render_synthesis(question: str, timestamp: datetime, selected: list[dict[str, Any]]) -> str:
    sources_field = ", ".join(f'"{entry["path"]}"' for entry in selected)
    question_yaml = question.replace('"', '\\"')
    conclusions = [entry["preview"] for entry in selected if entry["preview"]][:3]
    uncertainty: list[str] = []
    categories = sorted({entry["category"] for entry in selected if entry["category"]})
    source_paths = sorted({entry["source_path"] for entry in selected if entry["source_path"]})
    if len(source_paths) > 1:
        uncertainty.append("This answer spans multiple underlying sources and may still need human synthesis across them.")
    if len(categories) > 1:
        uncertainty.append(f"The evidence spans multiple categories: {', '.join(categories)}.")
    if not selected:
        uncertainty.append("No wiki pages matched the question strongly enough for grounded synthesis.")

    lines = [
        "---",
        f'mode: "synthesize"',
        f'question: "{question_yaml}"',
        f'asked_at: "{timestamp.date().isoformat()}"',
        f"sources: [{sources_field}]",
        'type: "qa-output"',
        "---",
        "",
        f"# {question}",
        "",
        "## Conclusion",
        "",
    ]
    if conclusions:
        for conclusion in conclusions:
            lines.append(f"- {conclusion}")
    else:
        lines.append("- No grounded conclusion available from the current wiki state.")
    lines.extend(["", "## Evidence", ""])
    for entry in selected:
        lines.append(f"### [[{Path(entry['path']).with_suffix('').as_posix()}|{entry['title']}]]")
        if entry["preview"]:
            lines.append(entry["preview"])
        if entry["headings"]:
            lines.append("")
            lines.append("Key headings: " + ", ".join(entry["headings"]))
        lines.append("")
    lines.extend(["## Uncertainty / Conflicts", ""])
    if uncertainty:
        for item in uncertainty:
            lines.append(f"- {item}")
    else:
        lines.append("- No explicit conflicts detected in the selected wiki pages.")
    lines.extend(["", "## Cited Pages", ""])
    for entry in selected:
        lines.append(f"- [[{Path(entry['path']).with_suffix('').as_posix()}]]")
    lines.append("")
    return "\n".join(lines)


def _write_query_note(
    layout: KBLayout,
    question: str,
    output_path: Path,
    selected: list[dict[str, Any]],
    rendered_output: str,
) -> tuple[Path, Path, str]:
    slug = _query_slug(question)
    output_rel = output_path.relative_to(layout.root).as_posix()
    content_hash = _content_hash(question, selected, rendered_output)
    versions = _query_versions(layout, slug)

    if versions and versions[-1]["content_hash"] == content_hash:
        latest = versions[-1]
        output_paths = latest["outputs"]
        if output_rel not in output_paths:
            output_paths.append(output_rel)
        _write_query_version(
            latest["path"],
            question,
            selected,
            rendered_output,
            output_paths,
            latest["version"],
            slug,
            str(parse_frontmatter(latest["path"].read_text(encoding="utf-8", errors="replace")).get("previous_version", "")),
            content_hash,
        )
        versions[-1] = {
            **latest,
            "outputs": output_paths,
            "content_hash": content_hash,
        }
        index_path = _write_query_history_index(layout, question, slug, versions)
        return latest["path"], index_path, "merged"

    next_version = versions[-1]["version"] + 1 if versions else 1
    version_path = layout.wiki_queries_dir / f"{slug}--v{next_version}.md"
    previous_version = versions[-1]["rel_path"] if versions else ""
    _write_query_version(
        version_path,
        question,
        selected,
        rendered_output,
        [output_rel],
        next_version,
        slug,
        previous_version,
        content_hash,
    )
    versions.append({
        "path": version_path,
        "rel_path": version_path.relative_to(layout.root).as_posix(),
        "version": next_version,
        "content_hash": content_hash,
        "outputs": [output_rel],
        "question": question,
    })
    index_path = _write_query_history_index(layout, question, slug, versions)
    action = "created" if next_version == 1 else "versioned"
    return version_path, index_path, action


def run_query(
    kb_root: Path,
    question: str,
    limit: int = 5,
    update_registry: bool = False,
    mode: str = "scaffold",
    file_back: bool = False,
) -> Result:
    """Resolve relevant wiki notes and materialize a markdown answer artifact."""
    layout = KBLayout(kb_root.resolve())
    state = _load_state(layout)
    result = Result(
        ok=True,
        action="kb_query",
        inputs={
            "kb_root": str(layout.root),
            "question": question,
            "limit": limit,
            "mode": mode,
            "file_back": file_back,
        },
    )

    note_entries = _score_notes(layout, question)
    selected = note_entries[:limit]
    timestamp = datetime.now(timezone.utc)
    slug = _query_slug(question)
    output_path = layout.outputs_qa_dir / f"{timestamp.strftime('%Y%m%d-%H%M%S')}-{slug}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rendered_output = _render_scaffold(question, timestamp, selected) if mode == "scaffold" else _render_synthesis(question, timestamp, selected)
    output_path.write_text(rendered_output + "\n", encoding="utf-8")

    filed_back_path: Path | None = None
    filed_back_index_path: Path | None = None
    file_back_action = ""
    touched_pages = [output_path.relative_to(layout.root).as_posix()]
    if file_back:
        filed_back_path, filed_back_index_path, file_back_action = _write_query_note(layout, question, output_path, selected, rendered_output)
        refresh_wiki_index(layout.root, layout.wiki_dir, schema_path=layout.kb_schema_path)
        touched_pages.append(filed_back_path.relative_to(layout.root).as_posix())
        touched_pages.append(filed_back_index_path.relative_to(layout.root).as_posix())
        touched_pages.append(layout.wiki_log_path.relative_to(layout.root).as_posix())

    if update_registry or file_back:
        from kb_creator.registry import build_registry

        build_registry(layout.root, artifacts_dir=layout.artifacts_dir)

    state.last_query_output = str(output_path.relative_to(layout.root))
    state.last_query_sources = [entry["path"] for entry in selected]
    if filed_back_path is not None:
        state.last_filed_query = filed_back_path.relative_to(layout.root).as_posix()
        refresh_wiki_index(layout.root, layout.wiki_dir, schema_path=layout.kb_schema_path)
        state.last_log_entry = append_log_entry(
            layout.wiki_log_path,
            "query",
            f"{file_back_action.title()} query note for '{question}'",
            touched_sources=sorted({entry["source_path"] for entry in selected if entry["source_path"]}),
            touched_pages=touched_pages,
        )
    state.phase = "query"
    state.save(layout.root)

    result.outputs = {
        "answer_path": str(output_path),
        "source_count": len(selected),
        "sources": selected,
        "mode": mode,
        "filed_back_path": str(filed_back_path) if filed_back_path is not None else "",
        "filed_back_index_path": str(filed_back_index_path) if filed_back_index_path is not None else "",
        "file_back_action": file_back_action,
    }
    return result
