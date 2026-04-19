"""Two-tier book build and root distillation workflows."""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result
from kb_creator.converter import convert_file
from kb_creator.kb import _load_state, _slugify, _title_from_markdown, compile_kb, init_kb
from kb_creator.permits import (
    APPLY_ROOT_PROMOTION_SCOPE,
    BUILD_BOOK_SCOPE,
    issue_write_permit,
    validate_write_permit,
)
from kb_creator.scanner import IGNORE_DIRS, SUPPORTED_EXTENSIONS
from kb_creator.source_patch import apply_layout_patches
from kb_creator.source_qa import run_layout_qa
from kb_creator.splitter import DEFAULT_MAX_LINES, DEFAULT_MIN_LINES, DEFAULT_PATTERNS, split_file
from kb_creator.state import BOOK_STAGE_NAMES, KBState
from kb_creator.wiki_ops import parse_frontmatter, summarize_markdown


INDEX_FILENAME = "DISTILLED_INDEX.md"
ROOT_INDEX_FILENAME = "DISTILLED_ROOT_INDEX.md"


@dataclass(frozen=True)
class VaultLayout:
    """Canonical two-tier vault layout."""

    root: Path

    @property
    def raw_dir(self) -> Path:
        return self.root / "raw"

    @property
    def raw_sources_dir(self) -> Path:
        return self.raw_dir / "sources"

    @property
    def raw_chapters_dir(self) -> Path:
        return self.raw_dir / "chapters"

    @property
    def artifacts_dir(self) -> Path:
        return self.root / ".kb-artifacts"

    @property
    def permits_dir(self) -> Path:
        return self.artifacts_dir / "permits"

    @property
    def worksets_dir(self) -> Path:
        return self.artifacts_dir / "root-promotion"

    @property
    def tombstones_dir(self) -> Path:
        return self.artifacts_dir / "tombstones"

    def book_dir(self, book_title: str) -> Path:
        name = _safe_display_name(book_title)
        if not name.endswith("知识库"):
            name = f"{name}知识库"
        return self.root / name

    def raw_source_path(self, book_title: str) -> Path:
        return self.raw_sources_dir / f"{_safe_display_name(book_title)}.md"

    def chapter_dir(self, book_title: str) -> Path:
        return self.raw_chapters_dir / _safe_display_name(book_title)


def _safe_display_name(value: str) -> str:
    sanitized = re.sub(r'[\\/:*?"<>|]+', "-", value.strip())
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized.strip() or "untitled"


def _section_name(value: str) -> str:
    section = re.sub(r'[\\/:*?"<>|]+', " ", value.strip())
    section = re.sub(r"^\d+\s*", "", section)
    section = re.sub(r"^[\W_]+", "", section)
    section = re.sub(r"\s+", " ", section)
    return section.strip() or "Notes"


def _note_filename(title: str) -> str:
    return _safe_display_name(title).replace("/", "-") + ".md"


def _ensure_vault_layout(layout: VaultLayout) -> None:
    for path in (
        layout.raw_sources_dir,
        layout.raw_chapters_dir,
        layout.artifacts_dir,
        layout.permits_dir,
        layout.worksets_dir,
        layout.tombstones_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)


def _load_root_state(layout: VaultLayout) -> KBState:
    state = KBState.load(layout.root)
    if state is None:
        state = KBState(
            kb_root=str(layout.root),
            output_dir=str(layout.root),
            raw_dir=str(layout.raw_dir.relative_to(layout.root)),
            artifacts_dir=str(layout.artifacts_dir.relative_to(layout.root)),
        )
    state.kb_root = str(layout.root)
    state.output_dir = str(layout.root)
    state.raw_dir = str(layout.raw_dir.relative_to(layout.root))
    state.artifacts_dir = str(layout.artifacts_dir.relative_to(layout.root))
    state.ensure_books()
    return state


def _iter_supported_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        rel = path.relative_to(root)
        if any(part in IGNORE_DIRS or part.startswith(".") for part in rel.parts):
            continue
        files.append(path)
    return files


def _resolve_book_sources(book_source: Path) -> list[Path]:
    resolved = book_source.resolve()
    if resolved.is_file():
        return [resolved]
    if resolved.is_dir():
        files = _iter_supported_files(resolved)
        if files:
            return files
    return []


def _combine_converted_sources(
    input_paths: list[Path],
    *,
    tmp_dir: Path,
) -> tuple[str, str, list[str]]:
    sections: list[str] = []
    warnings: list[str] = []
    primary_title = ""
    for idx, input_path in enumerate(input_paths):
        convert = convert_file(input_path, tmp_dir)
        if not convert.ok:
            raise ValueError("; ".join(convert.errors))
        md_path = convert.outputs.get("md_path")
        if not isinstance(md_path, str):
            raise ValueError(f"conversion did not produce markdown for {input_path.name}")
        text = Path(md_path).read_text(encoding="utf-8", errors="replace")
        if idx == 0:
            primary_title = _title_from_markdown(text, input_path.stem)
        sections.extend([
            f"# {_title_from_markdown(text, input_path.stem)}",
            "",
            f"Source file: {input_path.name}",
            "",
            text.strip(),
            "",
        ])
        warnings.extend(convert.warnings)
    return "\n".join(section for section in sections if section is not None).strip() + "\n", primary_title, warnings


def _write_full_source(
    layout: VaultLayout,
    *,
    book_title: str,
    combined_text: str,
) -> Path:
    raw_path = layout.raw_source_path(book_title)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(combined_text, encoding="utf-8")
    return raw_path


def _split_config(config: dict[str, Any] | None) -> dict[str, Any]:
    current = dict(config or {})
    return {
        "patterns": current.get("patterns", DEFAULT_PATTERNS),
        "min_lines": current.get("min_lines", DEFAULT_MIN_LINES),
        "max_lines": current.get("max_lines", DEFAULT_MAX_LINES),
    }


def _augment_chapter_file(
    chapter_path: Path,
    *,
    book_slug: str,
    book_title: str,
    root_chapter_path: str,
    root_source_path: str,
    root_section: str,
) -> None:
    content = chapter_path.read_text(encoding="utf-8", errors="replace")
    if not content.startswith("---"):
        return
    end = content.find("---", 3)
    if end == -1:
        return
    frontmatter = content[3:end].strip()
    body = content[end + 3:]
    lines = frontmatter.splitlines()
    extras = [
        f'book_slug: "{book_slug}"',
        f'book_title: "{book_title.replace(chr(34), "\\\"")}"',
        f'root_chapter_path: "{root_chapter_path}"',
        f'root_source_path: "{root_source_path}"',
        f'root_section: "{root_section.replace(chr(34), "\\\"")}"',
    ]
    chapter_path.write_text("---\n" + "\n".join(lines + extras) + "\n---" + body, encoding="utf-8")


def _copy_chapters_into_book_kb(chapter_dir: Path, book_root: Path) -> list[str]:
    copied: list[str] = []
    book_sources_dir = book_root / "raw" / "sources"
    for chapter_path in sorted(chapter_dir.rglob("*.md")):
        dest = book_sources_dir / chapter_path.relative_to(chapter_dir)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(chapter_path, dest)
        copied.append(dest.relative_to(book_root).as_posix())
    return copied


def _reset_book_runtime(book_root: Path) -> None:
    for rel in ("raw", "wiki", "outputs", ".kb-artifacts"):
        path = book_root / rel
        if path.exists():
            shutil.rmtree(path)
    for rel in ("KB_SCHEMA.md", ".kb-state.json"):
        path = book_root / rel
        if path.exists():
            path.unlink()


def _remove_generated_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _safe_root_target(root: Path, target_rel: str) -> Path:
    candidate = Path(target_rel)
    if candidate.is_absolute():
        raise ValueError(f"root promotion target must be relative: {target_rel}")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"root promotion target escapes vault root: {target_rel}")
    return resolved


def _refresh_distilled_indexes(layout: VaultLayout, state: KBState, touched_sections: set[str]) -> None:
    for section in sorted(touched_sections):
        section_dir = layout.root / section
        note_paths = [
            layout.root / rel
            for book in state.books.values()
            for rel in book.get("root_notes", [])
            if rel.startswith(f"{section}/") and (layout.root / rel).exists()
        ]
        index_path = section_dir / INDEX_FILENAME
        if not note_paths:
            if index_path.exists():
                index_path.unlink()
            continue
        lines = [
            "---",
            'type: "distilled-index"',
            f'section: "{section}"',
            "---",
            "",
            f"# {section}",
            "",
        ]
        for note_path in sorted(note_paths):
            title = parse_frontmatter(note_path.read_text(encoding="utf-8", errors="replace")).get("title", note_path.stem)
            lines.append(f"- [[{note_path.relative_to(layout.root).with_suffix('').as_posix()}|{title}]]")
        lines.append("")
        index_path.write_text("\n".join(lines), encoding="utf-8")

    root_index = layout.root / ROOT_INDEX_FILENAME
    section_counts: dict[str, int] = {}
    for book in state.books.values():
        for rel_path in book.get("root_notes", []):
            if (layout.root / rel_path).exists():
                section = Path(rel_path).parts[0]
                section_counts[section] = section_counts.get(section, 0) + 1
    lines = [
        "---",
        'type: "distilled-index"',
        'index_kind: "root-distillation"',
        "---",
        "",
        "# Root Distillation Index",
        "",
    ]
    for section in sorted(section_counts):
        lines.append(f"- [[{section}/{INDEX_FILENAME[:-3]}|{section}]] ({section_counts[section]} notes)")
    lines.append("")
    root_index.write_text("\n".join(lines), encoding="utf-8")


def _tombstone_missing_books(layout: VaultLayout, state: KBState) -> list[str]:
    touched_sections: set[str] = set()
    tombstoned: list[str] = []
    for book_slug, book in sorted(state.ensure_books().items()):
        source_path = book.get("source_path", "")
        if not source_path or book.get("tombstoned"):
            continue
        if Path(source_path).exists():
            continue

        for rel_path in book.get("root_notes", []):
            touched_sections.add(Path(rel_path).parts[0])
            _remove_generated_path(layout.root / rel_path)
        for key in ("raw_source_path", "chapter_dir", "book_kb_path"):
            rel_path = book.get(key, "")
            if rel_path:
                _remove_generated_path(layout.root / rel_path)

        tombstone_payload = {
            "book_slug": book_slug,
            "book_title": book.get("book_title", book_slug),
            "source_path": source_path,
            "tombstoned_at": datetime.now(timezone.utc).isoformat(),
            "removed_root_notes": book.get("root_notes", []),
        }
        tombstone_path = layout.tombstones_dir / f"{book_slug}.json"
        tombstone_path.parent.mkdir(parents=True, exist_ok=True)
        tombstone_path.write_text(json.dumps(tombstone_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        state.upsert_book(
            book_slug,
            tombstoned=True,
            review_needed=False,
            promotion_blocked=False,
            root_notes=[],
            tombstone_path=tombstone_path.relative_to(layout.root).as_posix(),
            stages={stage: False for stage in BOOK_STAGE_NAMES},
        )
        tombstoned.append(book_slug)

    if touched_sections:
        _refresh_distilled_indexes(layout, state, touched_sections)
    return tombstoned


def build_book(
    vault_root: Path,
    book_source: Path,
    *,
    permit_path: Path,
    split_config: dict[str, Any] | None = None,
    patch_queue_path: Path | None = None,
) -> Result:
    """Extract one book, build chapter archives, and materialize one book-local KB."""
    layout = VaultLayout(vault_root.resolve())
    _ensure_vault_layout(layout)
    state = _load_root_state(layout)
    tombstoned = _tombstone_missing_books(layout, state)

    input_paths = _resolve_book_sources(book_source)
    result = Result(
        ok=True,
        action="build_book",
        inputs={
            "vault_root": str(layout.root),
            "book_source": str(book_source.resolve()),
            "permit_path": str(permit_path.resolve()),
        },
    )
    if not input_paths:
        return Result(ok=False, action="build_book", inputs=result.inputs, errors=[f"book source not found or contains no supported files: {book_source}"])

    tmp_dir = layout.artifacts_dir / "tmp-build"
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    try:
        combined_text, primary_title, convert_warnings = _combine_converted_sources(input_paths, tmp_dir=tmp_dir)
    except ValueError as exc:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return Result(ok=False, action="build_book", inputs=result.inputs, errors=[str(exc)])
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    book_title = primary_title or book_source.stem
    book_slug = _slugify(book_title)
    permit_ok, permit_error = validate_write_permit(
        permit_path.resolve(),
        expected_scope=BUILD_BOOK_SCOPE,
        expected_target=book_slug,
        vault_root=layout.root,
    )
    if not permit_ok:
        return Result(ok=False, action="build_book", inputs=result.inputs, errors=[permit_error])

    raw_source_path = _write_full_source(layout, book_title=book_title, combined_text=combined_text)
    chapter_dir = layout.chapter_dir(book_title)
    if chapter_dir.exists():
        shutil.rmtree(chapter_dir)
    chapter_dir.mkdir(parents=True, exist_ok=True)

    split_result = split_file(
        raw_source_path,
        chapter_dir,
        _split_config(split_config),
        source_meta={
            "parent": book_title,
            "book_slug": book_slug,
            "book_title": book_title,
        },
    )
    if not split_result.ok:
        return split_result

    chapter_paths = [Path(path) for path in split_result.outputs.get("file_map", {}).values()]
    chapter_count = len(chapter_paths)
    root_source_rel = raw_source_path.relative_to(layout.root).as_posix()
    for chapter_path in chapter_paths:
        root_chapter_rel = chapter_path.relative_to(layout.root).as_posix()
        frontmatter = parse_frontmatter(chapter_path.read_text(encoding="utf-8", errors="replace"))
        root_section = _section_name(str(frontmatter.get("chapter", chapter_path.stem)))
        _augment_chapter_file(
            chapter_path,
            book_slug=book_slug,
            book_title=book_title,
            root_chapter_path=root_chapter_rel,
            root_source_path=root_source_rel,
            root_section=root_section,
        )

    chapter_artifacts = chapter_dir / ".kb-artifacts"
    qa_result = run_layout_qa(chapter_dir, artifacts_dir=chapter_artifacts)
    if not qa_result.ok:
        return qa_result
    qa_candidate_count = int(qa_result.outputs.get("candidate_count", 0))
    patch_applied = False
    patch_report_path = ""
    if patch_queue_path is not None:
        patch_result = apply_layout_patches(
            chapter_dir,
            queue_path=patch_queue_path.resolve(),
            candidates_path=Path(qa_result.artifacts["layout_candidates"]),
            artifacts_dir=chapter_artifacts,
        )
        patch_report_path = patch_result.outputs.get("report_path", "")
        patch_applied = patch_result.ok and patch_result.outputs.get("applied_count", 0) > 0
        if not patch_result.ok:
            return patch_result
        qa_result = run_layout_qa(chapter_dir, artifacts_dir=chapter_artifacts)
        qa_candidate_count = int(qa_result.outputs.get("candidate_count", 0))

    book_root = layout.book_dir(book_title)
    _reset_book_runtime(book_root)
    init_kb(book_root)
    copied_chapters = _copy_chapters_into_book_kb(chapter_dir, book_root)
    compile_result = compile_kb(book_root, force=True, emit_workset=True)
    if not compile_result.ok:
        return compile_result

    review_needed = qa_candidate_count > 0
    promotion_blocked = review_needed
    book_rel = book_root.relative_to(layout.root).as_posix()
    state.upsert_book(
        book_slug,
        book_title=book_title,
        source_path=str(book_source.resolve()),
        raw_source_path=raw_source_path.relative_to(layout.root).as_posix(),
        chapter_dir=chapter_dir.relative_to(layout.root).as_posix(),
        book_kb_path=book_rel,
        last_compile_workset=str(Path(compile_result.artifacts["compile_workset"]).relative_to(layout.root)),
        last_layout_candidates=str(Path(qa_result.artifacts["layout_candidates"]).relative_to(layout.root)),
        last_patch_report=Path(patch_report_path).resolve().relative_to(layout.root).as_posix() if patch_report_path else "",
        qa_candidate_count=qa_candidate_count,
        review_needed=review_needed,
        promotion_blocked=promotion_blocked,
        tombstoned=False,
        split_config=_split_config(split_config),
        last_permit_path=permit_path.resolve().relative_to(layout.root).as_posix() if permit_path.resolve().is_relative_to(layout.root) else str(permit_path.resolve()),
        stages={
            "extract_complete": True,
            "split_complete": True,
            "layout_qa_complete": True,
            "patches_applied": patch_applied,
            "book_compiled": True,
            "distill_ready": not review_needed,
            "root_promotion_applied": False,
        },
    )
    state.last_permit_path = str(permit_path.resolve())
    state.phase = "build-book"
    state.save(layout.root)

    build_report = {
        "book_slug": book_slug,
        "book_title": book_title,
        "raw_source_path": raw_source_path.relative_to(layout.root).as_posix(),
        "chapter_dir": chapter_dir.relative_to(layout.root).as_posix(),
        "book_kb_path": book_rel,
        "chapter_count": chapter_count,
        "copied_chapters": copied_chapters,
        "qa_candidate_count": qa_candidate_count,
        "review_needed": review_needed,
        "promotion_blocked": promotion_blocked,
        "tombstoned_books": tombstoned,
    }
    result.save_artifact(f"book-build/{book_slug}-report", build_report, layout.artifacts_dir)
    result.outputs = {
        "book_slug": book_slug,
        "book_title": book_title,
        "book_kb_path": book_rel,
        "raw_source_path": raw_source_path.relative_to(layout.root).as_posix(),
        "chapter_dir": chapter_dir.relative_to(layout.root).as_posix(),
        "chapter_count": chapter_count,
        "review_needed": review_needed,
        "promotion_blocked": promotion_blocked,
        "qa_candidate_count": qa_candidate_count,
        "compile_workset_path": str(Path(compile_result.artifacts["compile_workset"]).relative_to(layout.root)),
        "layout_candidates_path": str(Path(qa_result.artifacts["layout_candidates"]).relative_to(layout.root)),
        "build_report_path": result.artifacts[f"book-build/{book_slug}-report"],
        "tombstoned_books": tombstoned,
    }
    if convert_warnings:
        result.warnings.extend(convert_warnings)
    if review_needed:
        result.warnings.append("book build completed in review-needed state; root distillation is blocked until QA issues are resolved or waived")
    return result


def distill_to_root(vault_root: Path, book_kb: Path) -> Result:
    """Emit a root-promotion workset from one book-local KB."""
    layout = VaultLayout(vault_root.resolve())
    _ensure_vault_layout(layout)
    state = _load_root_state(layout)
    tombstoned = _tombstone_missing_books(layout, state)

    book_root = book_kb.resolve()
    if not book_root.is_dir():
        return Result(ok=False, action="distill_to_root", errors=[f"book KB not found: {book_kb}"])

    book_rel = book_root.relative_to(layout.root).as_posix()
    book_slug = next((slug for slug, payload in state.books.items() if payload.get("book_kb_path") == book_rel), "")
    if not book_slug:
        return Result(ok=False, action="distill_to_root", errors=[f"book KB is not registered in vault state: {book_rel}"])

    book = state.books[book_slug]
    if book.get("review_needed"):
        return Result(
            ok=False,
            action="distill_to_root",
            errors=[f"book `{book_slug}` is still in review-needed state; resolve or waive QA findings before root distillation"],
        )

    proposals: list[dict[str, Any]] = []
    used_targets: set[str] = set()
    summaries_root = book_root / "wiki" / "summaries"
    for summary_path in sorted(summaries_root.rglob("*.md")):
        rel_summary = summary_path.relative_to(layout.root).as_posix()
        content = summary_path.read_text(encoding="utf-8", errors="replace")
        frontmatter = parse_frontmatter(content)
        source_rel = frontmatter.get("source_path", "")
        root_chapter_path = ""
        root_section = _section_name(str(frontmatter.get("category", "Notes")))
        if isinstance(source_rel, str) and source_rel:
            source_path = book_root / source_rel
            if source_path.exists():
                source_frontmatter = parse_frontmatter(source_path.read_text(encoding="utf-8", errors="replace"))
                root_chapter_path = str(source_frontmatter.get("root_chapter_path", ""))
                root_section = _section_name(str(source_frontmatter.get("root_section", root_section)))
        title = str(frontmatter.get("title", summary_path.stem))
        target_filename = _note_filename(title)
        target_path = Path(root_section) / target_filename
        if target_path.as_posix() in used_targets:
            target_path = Path(root_section) / _note_filename(f"{title}-{summary_path.stem}")
        used_targets.add(target_path.as_posix())
        proposals.append({
            "proposal_id": f"{book_slug}:{summary_path.stem}",
            "book_slug": book_slug,
            "book_title": book.get("book_title", book_slug),
            "target_section": root_section,
            "target_path": target_path.as_posix(),
            "title": title,
            "source_page": rel_summary,
            "root_chapter_path": root_chapter_path,
            "summary": summarize_markdown(content, max_chars=420),
            "headings": frontmatter.get("headings", []),
        })

    workset = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "book_slug": book_slug,
        "book_title": book.get("book_title", book_slug),
        "book_kb_path": book_rel,
        "proposals": proposals,
    }
    result = Result(
        ok=True,
        action="distill_to_root",
        inputs={"vault_root": str(layout.root), "book_kb": book_rel},
    )
    result.save_artifact(f"root-promotion/{book_slug}-workset", workset, layout.artifacts_dir)
    workset_rel = Path(result.artifacts[f"root-promotion/{book_slug}-workset"]).relative_to(layout.root).as_posix()
    state.last_root_promotion_workset = workset_rel
    state.upsert_book(book_slug, last_root_promotion_workset=workset_rel)
    state.phase = "distill-to-root"
    state.save(layout.root)
    result.outputs = {
        "book_slug": book_slug,
        "book_title": book.get("book_title", book_slug),
        "proposal_count": len(proposals),
        "workset_path": workset_rel,
        "tombstoned_books": tombstoned,
    }
    return result


def _render_root_note(proposal: dict[str, Any], *, workset_path: str) -> str:
    title = proposal["title"].replace('"', '\\"')
    source_page = proposal["source_page"]
    root_chapter_path = proposal.get("root_chapter_path", "")
    sources_field = f'"{source_page}"'
    chapter_field = f'"{root_chapter_path}"' if root_chapter_path else ""
    lines = [
        "---",
        f'title: "{title}"',
        'type: "distilled-note"',
        f'section: "{proposal["target_section"].replace(chr(34), "\\\"")}"',
        f'book_slug: "{proposal["book_slug"]}"',
        f'book_title: "{proposal["book_title"].replace(chr(34), "\\\"")}"',
        f"source_pages: [{sources_field}]",
        f"root_chapter_paths: [{chapter_field}]" if chapter_field else "root_chapter_paths: []",
        f'generated_from_workset: "{workset_path}"',
        "---",
        "",
        f"# {proposal['title']}",
        "",
        proposal["summary"] or "_No summary available._",
        "",
        "## Provenance",
        "",
        f"- Summary page: [[{Path(source_page).with_suffix('').as_posix()}]]",
    ]
    if root_chapter_path:
        lines.append(f"- Chapter archive: [[{Path(root_chapter_path).with_suffix('').as_posix()}]]")
    lines.append("")
    return "\n".join(lines)


def apply_root_promotion(
    vault_root: Path,
    promotion_workset: Path,
    *,
    permit_path: Path,
) -> Result:
    """Apply one root-promotion workset with single-writer conflict handling."""
    layout = VaultLayout(vault_root.resolve())
    _ensure_vault_layout(layout)
    state = _load_root_state(layout)
    tombstoned = _tombstone_missing_books(layout, state)

    workset_path = promotion_workset.resolve()
    if not workset_path.exists():
        return Result(ok=False, action="apply_root_promotion", errors=[f"promotion workset not found: {promotion_workset}"])

    workset = json.loads(workset_path.read_text(encoding="utf-8"))
    book_slug = str(workset.get("book_slug", ""))
    if not book_slug or book_slug not in state.books:
        return Result(ok=False, action="apply_root_promotion", errors=["promotion workset refers to an unknown tracked book"])

    permit_ok, permit_error = validate_write_permit(
        permit_path.resolve(),
        expected_scope=APPLY_ROOT_PROMOTION_SCOPE,
        expected_target=book_slug,
        vault_root=layout.root,
    )
    if not permit_ok:
        return Result(ok=False, action="apply_root_promotion", errors=[permit_error])

    book = state.books[book_slug]
    if book.get("review_needed"):
        return Result(ok=False, action="apply_root_promotion", errors=[f"book `{book_slug}` is blocked from root promotion while review-needed remains true"])

    result = Result(
        ok=True,
        action="apply_root_promotion",
        inputs={
            "vault_root": str(layout.root),
            "promotion_workset": str(workset_path),
            "permit_path": str(permit_path.resolve()),
        },
    )

    desired_notes: list[str] = []
    applied = 0
    skipped = 0
    conflicts: list[dict[str, str]] = []
    touched_sections: set[str] = set()

    for proposal in workset.get("proposals", []):
        target_rel = proposal["target_path"]
        try:
            target_path = _safe_root_target(layout.root, target_rel)
        except ValueError as exc:
            conflicts.append({
                "target_path": target_rel,
                "reason": str(exc),
            })
            continue
        target_path.parent.mkdir(parents=True, exist_ok=True)
        touched_sections.add(Path(target_rel).parts[0])
        desired_notes.append(target_rel)
        rendered = _render_root_note(proposal, workset_path=workset_path.relative_to(layout.root).as_posix())
        if target_path.exists():
            existing_content = target_path.read_text(encoding="utf-8", errors="replace")
            existing_frontmatter = parse_frontmatter(existing_content)
            if existing_frontmatter.get("book_slug") not in {"", proposal["book_slug"]}:
                conflicts.append({
                    "target_path": target_rel,
                    "reason": f"existing note belongs to book `{existing_frontmatter.get('book_slug', 'unknown')}`",
                })
                continue
            if existing_content == rendered:
                skipped += 1
                continue
        target_path.write_text(rendered, encoding="utf-8")
        applied += 1

    old_notes = set(book.get("root_notes", []))
    stale_notes = old_notes - set(desired_notes)
    for rel_path in sorted(stale_notes):
        touched_sections.add(Path(rel_path).parts[0])
        _remove_generated_path(layout.root / rel_path)

    state.upsert_book(
        book_slug,
        root_notes=sorted(desired_notes),
        review_needed=False,
        promotion_blocked=False,
        last_root_promotion_report=f"root-promotion/{book_slug}-report",
        stages={
            "root_promotion_applied": len(conflicts) == 0,
        },
    )
    state.last_root_promotion_report = f"root-promotion/{book_slug}-report.json"
    state.phase = "apply-root-promotion"
    _refresh_distilled_indexes(layout, state, touched_sections)
    state.save(layout.root)

    report = {
        "book_slug": book_slug,
        "applied_count": applied,
        "skipped_count": skipped,
        "conflicts": conflicts,
        "stale_notes_removed": sorted(stale_notes),
        "root_notes": sorted(desired_notes),
        "tombstoned_books": tombstoned,
    }
    result.save_artifact(f"root-promotion/{book_slug}-report", report, layout.artifacts_dir)
    result.outputs = {
        "book_slug": book_slug,
        "applied_count": applied,
        "skipped_count": skipped,
        "conflict_count": len(conflicts),
        "report_path": result.artifacts[f"root-promotion/{book_slug}-report"],
        "root_notes": sorted(desired_notes),
        "tombstoned_books": tombstoned,
    }
    if conflicts:
        result.ok = False
        result.errors.extend(f"{item['target_path']}: {item['reason']}" for item in conflicts)
    return result


def status_vault(vault_root: Path) -> Result:
    """Return two-tier vault status when the root is not itself a KB layout."""
    layout = VaultLayout(vault_root.resolve())
    _ensure_vault_layout(layout)
    state = _load_root_state(layout)
    tombstoned_now = _tombstone_missing_books(layout, state)
    state.phase = "status"
    state.save(layout.root)

    books = []
    ready = 0
    review_needed = 0
    promotion_blocked = 0
    tombstoned = 0
    for book_slug, book in sorted(state.books.items()):
        if book.get("tombstoned"):
            tombstoned += 1
        elif book.get("review_needed"):
            review_needed += 1
        elif book.get("promotion_blocked"):
            promotion_blocked += 1
        else:
            ready += 1
        books.append({
            "book_slug": book_slug,
            "book_title": book.get("book_title", book_slug),
            "source_path": book.get("source_path", ""),
            "book_kb_path": book.get("book_kb_path", ""),
            "qa_candidate_count": book.get("qa_candidate_count", 0),
            "review_needed": book.get("review_needed", False),
            "promotion_blocked": book.get("promotion_blocked", False),
            "tombstoned": book.get("tombstoned", False),
            "stages": book.get("stages", {}),
        })

    result = Result(ok=True, action="vault_status", inputs={"vault_root": str(layout.root)})
    result.outputs = {
        "tracked_books": len(state.books),
        "ready_books": ready,
        "review_needed_books": review_needed,
        "promotion_blocked_books": promotion_blocked,
        "tombstoned_books": tombstoned,
        "last_root_promotion_workset": state.last_root_promotion_workset,
        "last_root_promotion_report": state.last_root_promotion_report,
        "last_permit_path": state.last_permit_path,
        "books": books,
        "tombstoned_now": tombstoned_now,
    }
    return result


def issue_permit(vault_root: Path, *, scope: str, target: str, expires_in_seconds: int = 3600) -> Result:
    """Developer/debug helper for signed write permits."""
    mapping = {
        BUILD_BOOK_SCOPE.name: BUILD_BOOK_SCOPE,
        APPLY_ROOT_PROMOTION_SCOPE.name: APPLY_ROOT_PROMOTION_SCOPE,
    }
    if scope not in mapping:
        return Result(ok=False, action="issue_write_permit", errors=[f"unsupported permit scope: {scope}"])
    return issue_write_permit(
        vault_root.resolve(),
        scope=mapping[scope],
        target=target,
        expires_in_seconds=expires_in_seconds,
    )
