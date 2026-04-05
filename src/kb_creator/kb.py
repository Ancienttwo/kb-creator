"""Top-level KB repository operations.

These functions power the ``kb`` CLI while preserving the lower-level
stage commands in ``bin/kb-*.py``.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result
from kb_creator.converter import convert_file
from kb_creator.linker import link as link_wiki
from kb_creator.registry import build_registry
from kb_creator.scanner import scan
from kb_creator.state import KBState
from kb_creator.summarizer import extract as extract_summaries, inject as inject_summaries
from kb_creator.wiki_ops import (
    append_log_entry,
    refresh_wiki_index,
    render_kb_schema,
    summarize_markdown,
)


def _path_slug(path: Path) -> str:
    text = path.as_posix()
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[^\w.\-/\u3400-\u9fff]+", "-", text, flags=re.UNICODE)
    text = text.replace("/", "__")
    text = re.sub(r"[-_]{3,}", "__", text)
    return text.strip("-_") or "untitled"


def _slugify(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = re.sub(r"[^\w\s\-\u3400-\u9fff]+", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s/]+", "-", text)
    text = re.sub(r"-{2,}", "-", text)
    return text.strip("-") or "untitled"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _title_from_markdown(text: str, fallback: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
    return fallback


def _headings(text: str, limit: int = 8) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                headings.append(heading)
        if len(headings) >= limit:
            break
    return headings


def _first_paragraphs(text: str, max_chars: int = 700) -> str:
    body: list[str] = []
    in_code = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("|"):
            continue
        body.append(stripped)
        if sum(len(part) for part in body) >= max_chars:
            break
    summary = " ".join(body).strip()
    return summary[:max_chars].strip()


def _category_for(rel_path: Path) -> str:
    parts = rel_path.parts
    if len(parts) > 1:
        return parts[0]
    return "uncategorized"


def _concept_candidates(title: str, headings: list[str]) -> list[str]:
    stopwords = {
        "the", "and", "for", "with", "from", "that", "this", "into", "your",
        "using", "about", "over", "new", "all", "are", "its", "their",
    }
    ordered: list[str] = []
    seen: set[str] = set()

    def add(candidate: str) -> None:
        candidate = re.sub(r"\s+", " ", candidate.strip(" -:#`"))
        if not candidate:
            return
        key = candidate.casefold()
        if key in seen:
            return
        if len(candidate) < 3:
            return
        if key in stopwords:
            return
        seen.add(key)
        ordered.append(candidate)

    add(title)
    for heading in headings:
        add(heading)
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9+/.-]{2,}\b", " ".join([title] + headings)):
        add(token)
    return ordered[:10]


def _inline_list(values: list[str]) -> str:
    if not values:
        return "[]"
    escaped = [item.replace('"', '\\"') for item in values]
    return "[" + ", ".join(f'"{item}"' for item in escaped) + "]"


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _yaml_quote(text: str) -> str:
    return '"' + text.replace('"', '\\"') + '"'


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


@dataclass(frozen=True)
class KBLayout:
    """Canonical KB repository layout."""

    root: Path

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def raw_sources_dir(self) -> Path:
        return self.raw_dir / "sources"

    @property
    def raw_assets_dir(self) -> Path:
        return self.raw_dir / "assets"

    @property
    def wiki_dir(self) -> Path:
        return self.root / "wiki"

    @property
    def wiki_summaries_dir(self) -> Path:
        return self.wiki_dir / "summaries"

    @property
    def wiki_concepts_dir(self) -> Path:
        return self.wiki_dir / "concepts"

    @property
    def wiki_indexes_dir(self) -> Path:
        return self.wiki_dir / "indexes"

    @property
    def wiki_queries_dir(self) -> Path:
        return self.wiki_dir / "queries"

    @property
    def wiki_log_path(self) -> Path:
        return self.wiki_dir / "log.md"

    @property
    def outputs_dir(self) -> Path:
        return self.root / "outputs"

    @property
    def outputs_qa_dir(self) -> Path:
        return self.outputs_dir / "qa"

    @property
    def outputs_health_dir(self) -> Path:
        return self.outputs_dir / "health"

    @property
    def artifacts_dir(self) -> Path:
        return self.root / ".kb-artifacts"

    @property
    def kb_schema_path(self) -> Path:
        return self.root / "KB_SCHEMA.md"


def _ensure_layout(layout: KBLayout) -> None:
    for path in (
        layout.raw_sources_dir,
        layout.raw_assets_dir,
        layout.wiki_summaries_dir,
        layout.wiki_concepts_dir,
        layout.wiki_indexes_dir,
        layout.wiki_queries_dir,
        layout.outputs_qa_dir,
        layout.outputs_health_dir,
        layout.artifacts_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _ensure_static_files(layout: KBLayout) -> None:
    if not layout.kb_schema_path.exists():
        layout.kb_schema_path.write_text(render_kb_schema(), encoding="utf-8")
    if not layout.wiki_log_path.exists():
        layout.wiki_log_path.write_text("# KB Log\n\n", encoding="utf-8")
    if not (layout.wiki_dir / "index.md").exists():
        refresh_wiki_index(layout.root, layout.wiki_dir, schema_path=layout.kb_schema_path)


def _load_state(layout: KBLayout) -> KBState:
    state = KBState.load(layout.root)
    if state is None:
        state = KBState(
            kb_root=str(layout.root),
            output_dir=str(layout.root),
            raw_dir=str(layout.raw_dir.relative_to(layout.root)),
            wiki_dir=str(layout.wiki_dir.relative_to(layout.root)),
            outputs_dir=str(layout.outputs_dir.relative_to(layout.root)),
            artifacts_dir=str(layout.artifacts_dir.relative_to(layout.root)),
        )
    if not state.kb_root:
        state.kb_root = str(layout.root)
    if not state.output_dir:
        state.output_dir = str(layout.root)
    state.raw_dir = str(layout.raw_dir.relative_to(layout.root))
    state.wiki_dir = str(layout.wiki_dir.relative_to(layout.root))
    state.outputs_dir = str(layout.outputs_dir.relative_to(layout.root))
    state.artifacts_dir = str(layout.artifacts_dir.relative_to(layout.root))
    return state


def _write_sources_index(layout: KBLayout, source_rows: list[tuple[str, str, str]]) -> Path:
    sources_index = [
        "---",
        'type: "index"',
        'index_kind: "sources"',
        "---",
        "",
        "# All Sources",
        "",
    ]
    for title, raw_path, summary_path in sorted(source_rows):
        sources_index.append(f"- [[{Path(summary_path).with_suffix('').as_posix()}|{title}]] (`{raw_path}`)")
    index_path = layout.wiki_indexes_dir / "all-sources.md"
    index_path.write_text("\n".join(sources_index) + "\n", encoding="utf-8")
    return index_path


def _write_concepts_index(layout: KBLayout, concept_rows: list[tuple[str, str]]) -> Path:
    concepts_index = [
        "---",
        'type: "index"',
        'index_kind: "concepts"',
        "---",
        "",
        "# All Concepts",
        "",
    ]
    for title, rel_path in concept_rows:
        concepts_index.append(f"- [[{Path(rel_path).with_suffix('').as_posix()}|{title}]]")
    index_path = layout.wiki_indexes_dir / "all-concepts.md"
    index_path.write_text("\n".join(concepts_index) + "\n", encoding="utf-8")
    return index_path


def _pages_matching_terms(layout: KBLayout, terms: list[str], exclude: set[str]) -> list[str]:
    matched: list[str] = []
    lowered_terms = [term.casefold() for term in terms if term]
    for note_path in sorted(layout.wiki_dir.rglob("*.md")):
        rel_path = note_path.relative_to(layout.root).as_posix()
        if rel_path in exclude:
            continue
        content = note_path.read_text(encoding="utf-8", errors="replace").casefold()
        stem = note_path.stem.casefold()
        for term in lowered_terms:
            if term and (term in content or term in stem):
                matched.append(rel_path)
                break
    return matched


def _build_workset_entry(
    layout: KBLayout,
    state: KBState,
    raw_rel: Path,
    title: str,
    headings: list[str],
    category: str,
    summary_rel: Path,
    concept_rels: list[Path],
    excerpt: str,
) -> dict[str, Any]:
    exclude = {
        summary_rel.as_posix(),
        "wiki/index.md",
    }
    category_pages = [
        path.relative_to(layout.root).as_posix()
        for path in sorted((layout.wiki_summaries_dir / category).glob("*.md"))
        if path.relative_to(layout.root).as_posix() != summary_rel.as_posix()
    ]
    concept_pages = [path.as_posix() for path in concept_rels]
    existing_concepts = [path for path in concept_pages if (layout.root / path).exists()]
    matched_pages = _pages_matching_terms(
        layout,
        [title] + headings[:4],
        exclude=exclude | set(category_pages) | set(existing_concepts),
    )
    recent_query_pages = list(state.last_query_sources)
    if state.last_filed_query:
        recent_query_pages.append(state.last_filed_query)
    existing_pages = _unique(category_pages + existing_concepts + matched_pages + recent_query_pages)

    evidence_snippets = [
        {"kind": "title", "text": title},
        {"kind": "excerpt", "text": excerpt[:280] or "_No summary candidate available._"},
    ]
    evidence_snippets.extend({"kind": "heading", "text": heading} for heading in headings[:4])

    return {
        "source_path": raw_rel.as_posix(),
        "summary_page": summary_rel.as_posix(),
        "candidate_concept_pages": concept_pages,
        "existing_pages_to_review": existing_pages,
        "evidence_snippets": evidence_snippets,
        "actions": [
            "refresh summary page",
            "review related concept pages",
            "check matched pages for contradictions or stale claims",
            "consider whether the source unlocks a follow-up query note",
        ],
    }


def init_kb(kb_root: Path) -> Result:
    """Initialize a KB repository layout."""
    layout = KBLayout(kb_root.resolve())
    _ensure_layout(layout)
    _ensure_static_files(layout)
    index_path = refresh_wiki_index(layout.root, layout.wiki_dir, schema_path=layout.kb_schema_path)
    state = _load_state(layout)
    state.phase = "init"
    state.save(layout.root)

    result = Result(ok=True, action="kb_init", inputs={"kb_root": str(layout.root)})
    result.outputs = {
        "kb_root": str(layout.root),
        "layout": {
            "raw": str(layout.raw_dir.relative_to(layout.root)),
            "wiki": str(layout.wiki_dir.relative_to(layout.root)),
            "outputs": str(layout.outputs_dir.relative_to(layout.root)),
            "artifacts": str(layout.artifacts_dir.relative_to(layout.root)),
        },
        "schema_path": str(layout.kb_schema_path.relative_to(layout.root)),
        "log_path": str(layout.wiki_log_path.relative_to(layout.root)),
        "index_path": str(index_path.relative_to(layout.root)),
    }
    return result


def ingest_kb(kb_root: Path, source_dir: Path, enhance_tables: bool = False) -> Result:
    """Normalize source documents into ``raw/sources``."""
    layout = KBLayout(kb_root.resolve())
    _ensure_layout(layout)
    _ensure_static_files(layout)
    state = _load_state(layout)

    result = Result(
        ok=True,
        action="kb_ingest",
        inputs={"kb_root": str(layout.root), "source_dir": str(source_dir.resolve())},
    )

    scan_result = scan(source_dir.resolve(), artifacts_dir=layout.artifacts_dir)
    if not scan_result.ok:
        return scan_result

    manifest = json.loads(Path(scan_result.artifacts["scan_report"]).read_text(encoding="utf-8"))
    ingested = 0
    skipped = 0
    failures: list[str] = []
    touched_sources: list[str] = []

    for entry in manifest:
        rel_source = Path(entry["path"])
        abs_source = source_dir / rel_source
        if not abs_source.exists():
            skipped += 1
            failures.append(f"missing source during ingest: {rel_source}")
            continue

        source_hash = _sha256(abs_source)
        category = _category_for(rel_source)
        raw_rel = Path("raw") / "sources" / rel_source.with_suffix(".md")
        raw_abs = layout.root / raw_rel
        raw_abs.parent.mkdir(parents=True, exist_ok=True)

        previous = state.files.get(rel_source.as_posix(), {})
        if (
            previous.get("hash") == source_hash
            and previous.get("raw_path") == raw_rel.as_posix()
            and raw_abs.exists()
        ):
            skipped += 1
            continue

        convert_result = convert_file(abs_source, raw_abs.parent, enhance_tables=enhance_tables)
        if not convert_result.ok:
            failures.extend(convert_result.errors)
            continue

        produced = Path(convert_result.outputs["md_path"])
        if produced != raw_abs:
            raw_abs.write_text(produced.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            if produced.exists():
                produced.unlink()

        state.mark_ingested(rel_source.as_posix(), raw_rel.as_posix(), source_hash, category=category)
        touched_sources.append(raw_rel.as_posix())
        ingested += 1

    if touched_sources or failures:
        state.last_log_entry = append_log_entry(
            layout.wiki_log_path,
            "ingest",
            f"Ingested {ingested} sources",
            touched_sources=touched_sources,
            touched_pages=[],
            warnings=failures,
        )

    state.source_dir = str(source_dir.resolve())
    state.phase = "ingest"
    state.save(layout.root)
    refresh_wiki_index(layout.root, layout.wiki_dir, schema_path=layout.kb_schema_path)

    result.outputs = {
        "ingested": ingested,
        "skipped": skipped,
        "total_sources": len(manifest),
        "raw_sources_dir": str(layout.raw_sources_dir),
    }
    if failures:
        result.warnings.extend(failures)
    return result


def compile_kb(kb_root: Path, force: bool = False, emit_workset: bool = False) -> Result:
    """Compile raw markdown into wiki summaries, concepts, and indexes."""
    layout = KBLayout(kb_root.resolve())
    _ensure_layout(layout)
    _ensure_static_files(layout)
    state = _load_state(layout)

    raw_files = sorted(layout.raw_sources_dir.rglob("*.md"))
    result = Result(
        ok=True,
        action="kb_compile",
        inputs={"kb_root": str(layout.root), "force": force, "emit_workset": emit_workset},
    )
    if not raw_files:
        result.warnings.append("No raw markdown sources found under raw/sources.")
        return result

    concept_map: dict[str, dict[str, Any]] = {}
    updated = 0
    skipped = 0
    source_rows: list[tuple[str, str, str]] = []
    workset_entries: list[dict[str, Any]] = []
    per_source_artifacts: dict[str, list[str]] = {}
    touched_pages: set[str] = set()
    touched_sources: list[str] = []

    source_snapshots: list[dict[str, Any]] = []
    for raw_file in raw_files:
        raw_rel = raw_file.relative_to(layout.root)
        source_key = next(
            (key for key, meta in state.files.items() if meta.get("raw_path") == raw_rel.as_posix()),
            raw_rel.as_posix(),
        )
        text = _read_text(raw_file)
        source_hash = _sha256(raw_file)
        title = _title_from_markdown(text, raw_file.stem)
        headings = _headings(text)
        category = _category_for(raw_file.relative_to(layout.raw_sources_dir))
        summary_key = _path_slug(raw_file.relative_to(layout.raw_sources_dir).with_suffix(""))
        summary_rel = Path("wiki") / "summaries" / category / f"{summary_key}.md"
        excerpt = _first_paragraphs(text)
        concepts = _concept_candidates(title, headings)
        source_snapshots.append({
            "source_key": source_key,
            "raw_rel": raw_rel,
            "source_hash": source_hash,
            "title": title,
            "headings": headings,
            "category": category,
            "summary_rel": summary_rel,
            "excerpt": excerpt,
            "concepts": concepts,
        })

    for snapshot in source_snapshots:
        source_key = snapshot["source_key"]
        raw_rel: Path = snapshot["raw_rel"]
        source_hash = snapshot["source_hash"]
        title = snapshot["title"]
        headings = snapshot["headings"]
        category = snapshot["category"]
        summary_rel: Path = snapshot["summary_rel"]
        excerpt = snapshot["excerpt"]
        concepts: list[str] = snapshot["concepts"]
        summary_abs = layout.root / summary_rel
        summary_abs.parent.mkdir(parents=True, exist_ok=True)

        entry = state.files.get(source_key, {})
        artifacts = entry.get("artifacts", [])
        dirty = force or not (
            entry.get("dirty") is False
            and
            entry.get("hash") == source_hash
            and summary_rel.as_posix() in artifacts
            and summary_abs.exists()
        )

        if not dirty:
            skipped += 1
        else:
            summary_body = [
                "---",
                f"title: {_yaml_quote(title)}",
                'type: "summary"',
                f"category: {_yaml_quote(category)}",
                f"source_path: {_yaml_quote(raw_rel.as_posix())}",
                f"source_key: {_yaml_quote(source_key)}",
                f"source_hash: {_yaml_quote(source_hash)}",
                f'headings: {_inline_list(headings[:8])}',
                "---",
                "",
                f"# {title}",
                "",
                f"Source: [[{raw_rel.with_suffix('').as_posix()}]]",
                "",
                "## Summary",
                "",
                excerpt or "_No summary candidate available._",
                "",
                "## Key Headings",
                "",
            ]
            if headings:
                summary_body.extend(f"- {heading}" for heading in headings[:8])
            else:
                summary_body.append("- _No headings detected_")
            summary_body.extend(["", "## Concepts", ""])
            if concepts:
                for concept in concepts:
                    summary_body.append(f"- [[{concept}]]")
            else:
                summary_body.append("- _No concepts extracted_")
            summary_abs.write_text("\n".join(summary_body) + "\n", encoding="utf-8")
            updated += 1
            touched_sources.append(raw_rel.as_posix())
            touched_pages.add(summary_rel.as_posix())

            concept_rels = [Path("wiki") / "concepts" / f"{_slugify(concept)}.md" for concept in concepts]
            workset_entries.append(
                _build_workset_entry(
                    layout,
                    state,
                    raw_rel,
                    title,
                    headings,
                    category,
                    summary_rel,
                    concept_rels,
                    excerpt,
                )
            )

        source_rows.append((title, raw_rel.as_posix(), summary_rel.as_posix()))
        source_artifacts = per_source_artifacts.setdefault(source_key, [])
        source_artifacts.append(summary_rel.as_posix())
        for concept in concepts:
            key = _slugify(concept)
            concept_entry = concept_map.setdefault(key, {"title": concept, "sources": [], "aliases": []})
            if concept not in concept_entry["aliases"]:
                concept_entry["aliases"].append(concept)
            if summary_rel.as_posix() not in concept_entry["sources"]:
                concept_entry["sources"].append(summary_rel.as_posix())
            source_artifacts.append((Path("wiki") / "concepts" / f"{key}.md").as_posix())

    concept_rows: list[tuple[str, str]] = []
    for key, concept in sorted(concept_map.items()):
        concept_rel = Path("wiki") / "concepts" / f"{key}.md"
        concept_abs = layout.root / concept_rel
        concept_abs.parent.mkdir(parents=True, exist_ok=True)
        concept_body = [
            "---",
            f"title: {_yaml_quote(concept['title'])}",
            'type: "concept"',
            f"concept_key: {_yaml_quote(key)}",
            f'aliases: {_inline_list(concept["aliases"])}',
            f'source_count: {len(concept["sources"])}',
            "---",
            "",
            f"# {concept['title']}",
            "",
            "## Related Summaries",
            "",
        ]
        concept_body.extend(f"- [[{Path(source).with_suffix('').as_posix()}]]" for source in concept["sources"])
        concept_abs.write_text("\n".join(concept_body) + "\n", encoding="utf-8")
        concept_rows.append((concept["title"], concept_rel.as_posix()))
        touched_pages.add(concept_rel.as_posix())

    sources_index = _write_sources_index(layout, source_rows)
    concepts_index = _write_concepts_index(layout, concept_rows)
    index_path = refresh_wiki_index(layout.root, layout.wiki_dir, schema_path=layout.kb_schema_path)
    touched_pages.update({
        sources_index.relative_to(layout.root).as_posix(),
        concepts_index.relative_to(layout.root).as_posix(),
        index_path.relative_to(layout.root).as_posix(),
    })

    global_pages = [
        sources_index.relative_to(layout.root).as_posix(),
        concepts_index.relative_to(layout.root).as_posix(),
        index_path.relative_to(layout.root).as_posix(),
    ]
    if emit_workset:
        result.save_artifact("compile_workset", {"sources": workset_entries}, layout.artifacts_dir)
        state.last_compile_workset = str(Path(result.artifacts["compile_workset"]).relative_to(layout.root))
        global_pages.append(state.last_compile_workset)

    for snapshot in source_snapshots:
        source_key = snapshot["source_key"]
        source_hash = snapshot["source_hash"]
        source_artifacts = _unique(per_source_artifacts.get(source_key, []) + global_pages)
        state.mark_compiled(source_key, source_hash, source_artifacts)

    next_questions = [
        f"Should an agent review {entry['summary_page']} and {len(entry['existing_pages_to_review'])} related pages?"
        for entry in workset_entries[:3]
    ]
    if touched_sources or emit_workset:
        state.last_log_entry = append_log_entry(
            layout.wiki_log_path,
            "compile",
            f"Compiled {updated} updated, {skipped} skipped sources",
            touched_sources=touched_sources,
            touched_pages=sorted(touched_pages),
            next_questions=next_questions,
        )

    state.phase = "compile"
    state.save(layout.root)

    result.outputs = {
        "total_sources": len(raw_files),
        "updated_summaries": updated,
        "skipped_sources": skipped,
        "concepts": len(concept_map),
        "indexes": global_pages[:3],
        "workset_sources": len(workset_entries),
    }
    return result


def link_kb(kb_root: Path, mode: str = "both", dry_run: bool = False) -> Result:
    """Run wiki linking against the compiled wiki directory."""
    layout = KBLayout(kb_root.resolve())
    _ensure_layout(layout)
    _ensure_static_files(layout)
    return link_wiki(layout.wiki_dir, mode=mode, dry_run=dry_run, artifacts_dir=layout.artifacts_dir)


def summarize_kb(
    kb_root: Path,
    extract: bool = False,
    inject_path: Path | None = None,
    fmt: str = "callout",
) -> Result:
    """Dispatch summary extract/inject against the compiled wiki."""
    layout = KBLayout(kb_root.resolve())
    _ensure_layout(layout)
    _ensure_static_files(layout)
    if extract:
        return extract_summaries(layout.wiki_dir, artifacts_dir=layout.artifacts_dir)
    if inject_path is not None:
        return inject_summaries(layout.wiki_dir, inject_path, fmt=fmt)
    return Result(ok=False, action="kb_summarize", errors=["must specify extract or inject"])


def registry_kb(kb_root: Path) -> Result:
    """Build an expanded registry from the KB root."""
    layout = KBLayout(kb_root.resolve())
    _ensure_layout(layout)
    _ensure_static_files(layout)
    state = _load_state(layout)
    result = build_registry(layout.root, artifacts_dir=layout.artifacts_dir)
    state.phase = "registry"
    state.save(layout.root)
    return result


def status_kb(kb_root: Path) -> Result:
    """Return KB repository counts and resumable state."""
    layout = KBLayout(kb_root.resolve())
    _ensure_layout(layout)
    _ensure_static_files(layout)
    state = _load_state(layout)

    raw_count = len(list(layout.raw_sources_dir.rglob("*.md")))
    wiki_count = len(list(layout.wiki_dir.rglob("*.md")))
    qa_count = len(list(layout.outputs_qa_dir.glob("*.md")))
    health_count = len(list(layout.outputs_health_dir.glob("health-*.md")))
    lint_count = len(list(layout.outputs_health_dir.glob("lint-*.md")))
    dirty = sum(1 for meta in state.files.values() if meta.get("dirty"))

    result = Result(ok=True, action="kb_status", inputs={"kb_root": str(layout.root)})
    result.outputs = {
        "phase": state.phase,
        "raw_sources": raw_count,
        "wiki_notes": wiki_count,
        "qa_outputs": qa_count,
        "health_reports": health_count,
        "lint_reports": lint_count,
        "tracked_sources": len(state.files),
        "dirty_sources": dirty,
        "last_health_report": state.last_health_report,
        "last_query_output": state.last_query_output,
        "last_filed_query": state.last_filed_query,
        "last_compile_workset": state.last_compile_workset,
        "last_log_entry": state.last_log_entry,
        "schema_path": str(layout.kb_schema_path.relative_to(layout.root)),
        "log_path": str(layout.wiki_log_path.relative_to(layout.root)),
        "progress": state.progress_summary(),
    }
    return result
