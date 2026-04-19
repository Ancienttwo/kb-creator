"""Console entrypoint for the top-level kb CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from kb_creator.build import (
    apply_root_promotion,
    build_book,
    distill_to_root,
    issue_permit,
    status_vault,
)
from kb_creator.contracts import fail
from kb_creator.health import run_health_checks
from kb_creator.kb import (
    compile_kb,
    ingest_kb,
    init_kb,
    link_kb,
    registry_kb,
    status_kb,
    summarize_kb,
)
from kb_creator.lint import run_lint_checks
from kb_creator.query import run_query


def _load_json_config(path: Path | None, *, action: str, label: str) -> dict:
    if path is None:
        return {}
    if not path.exists():
        fail(action, f"{label} not found: {path}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(action, f"failed to parse {label}: {exc}")
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="kb-creator top-level KB builder CLI")
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Initialize a KB repository")
    init_parser.add_argument("kb_root", type=Path)

    ingest_parser = subparsers.add_parser("ingest", help="Normalize source documents into raw/")
    ingest_parser.add_argument("kb_root", type=Path)
    ingest_parser.add_argument("source_dir", type=Path)
    ingest_parser.add_argument("--enhance-tables", action="store_true")

    compile_parser = subparsers.add_parser("compile", help="Compile raw sources into wiki/")
    compile_parser.add_argument("kb_root", type=Path)
    compile_parser.add_argument("--force", action="store_true")
    compile_parser.add_argument("--emit-workset", action="store_true")

    link_parser = subparsers.add_parser("link", help="Enrich wiki links")
    link_parser.add_argument("kb_root", type=Path)
    link_parser.add_argument("--mode", choices=["structural", "semantic", "both"], default="both")
    link_parser.add_argument("--dry-run", action="store_true")

    summarize_parser = subparsers.add_parser("summarize", help="Extract or inject summaries")
    summarize_parser.add_argument("kb_root", type=Path)
    summarize_parser.add_argument("--extract", action="store_true")
    summarize_parser.add_argument("--inject", type=Path, default=None)
    summarize_parser.add_argument("--format", choices=["callout", "frontmatter"], dest="fmt", default="callout")

    health_parser = subparsers.add_parser("health", help="Run KB health checks")
    health_parser.add_argument("kb_root", type=Path)

    lint_parser = subparsers.add_parser("lint", help="Run KB maintenance lint checks")
    lint_parser.add_argument("kb_root", type=Path)

    query_parser = subparsers.add_parser("query", help="Materialize a markdown query output")
    query_parser.add_argument("kb_root", type=Path)
    query_parser.add_argument("--question", required=True)
    query_parser.add_argument("--limit", type=int, default=5)
    query_parser.add_argument("--update-registry", action="store_true")
    query_parser.add_argument("--mode", choices=["scaffold", "synthesize"], default="scaffold")
    query_parser.add_argument("--file-back", choices=["yes", "no"], default="no")

    registry_parser = subparsers.add_parser("registry", help="Build the KB registry")
    registry_parser.add_argument("kb_root", type=Path)

    status_parser = subparsers.add_parser("status", help="Show KB repository status")
    status_parser.add_argument("kb_root", type=Path)

    permit_parser = subparsers.add_parser("issue-permit", help="Issue a signed write permit for debug/test workflows")
    permit_parser.add_argument("vault_root", type=Path)
    permit_parser.add_argument("--scope", required=True, choices=["build-book", "apply-root-promotion"])
    permit_parser.add_argument("--target", required=True)
    permit_parser.add_argument("--expires-in", type=int, default=3600)

    build_book_parser = subparsers.add_parser("build-book", help="Build one book-local KB from a source document")
    build_book_parser.add_argument("vault_root", type=Path)
    build_book_parser.add_argument("book_source", type=Path)
    build_book_parser.add_argument("--permit", required=True, type=Path)
    build_book_parser.add_argument("--split-config", type=Path, default=None)
    build_book_parser.add_argument("--patch-queue", type=Path, default=None)

    distill_parser = subparsers.add_parser("distill-to-root", help="Emit a root-promotion workset from a book-local KB")
    distill_parser.add_argument("vault_root", type=Path)
    distill_parser.add_argument("book_kb", type=Path)

    apply_promotion_parser = subparsers.add_parser("apply-root-promotion", help="Apply one root-promotion workset")
    apply_promotion_parser.add_argument("vault_root", type=Path)
    apply_promotion_parser.add_argument("promotion_workset", type=Path)
    apply_promotion_parser.add_argument("--permit", required=True, type=Path)

    args = parser.parse_args()

    if args.command == "init":
        result = init_kb(args.kb_root)
    elif args.command == "ingest":
        if not args.source_dir.is_dir():
            fail("kb_ingest", f"Source directory not found: {args.source_dir}")
        result = ingest_kb(args.kb_root, args.source_dir, enhance_tables=args.enhance_tables)
    elif args.command == "compile":
        result = compile_kb(args.kb_root, force=args.force, emit_workset=args.emit_workset)
    elif args.command == "link":
        result = link_kb(args.kb_root, mode=args.mode, dry_run=args.dry_run)
    elif args.command == "summarize":
        result = summarize_kb(args.kb_root, extract=args.extract, inject_path=args.inject, fmt=args.fmt)
    elif args.command == "health":
        result = run_health_checks(args.kb_root)
    elif args.command == "lint":
        result = run_lint_checks(args.kb_root)
    elif args.command == "query":
        result = run_query(
            args.kb_root,
            args.question,
            limit=args.limit,
            update_registry=args.update_registry,
            mode=args.mode,
            file_back=args.file_back == "yes",
        )
    elif args.command == "registry":
        result = registry_kb(args.kb_root)
    elif args.command == "status":
        if (args.kb_root / "wiki").is_dir():
            result = status_kb(args.kb_root)
        else:
            result = status_vault(args.kb_root)
    elif args.command == "issue-permit":
        result = issue_permit(args.vault_root, scope=args.scope, target=args.target, expires_in_seconds=args.expires_in)
    elif args.command == "build-book":
        split_config = _load_json_config(args.split_config, action="build_book", label="split config")
        result = build_book(
            args.vault_root,
            args.book_source,
            permit_path=args.permit,
            split_config=split_config,
            patch_queue_path=args.patch_queue,
        )
    elif args.command == "distill-to-root":
        result = distill_to_root(args.vault_root, args.book_kb)
    elif args.command == "apply-root-promotion":
        workset_path = args.promotion_workset
        if not workset_path.exists():
            candidate = args.vault_root / workset_path
            if candidate.exists():
                workset_path = candidate
        result = apply_root_promotion(args.vault_root, workset_path, permit_path=args.permit)
    else:
        fail("kb", "missing subcommand")
        return

    result.emit()
