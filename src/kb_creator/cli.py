"""Console entrypoint for the top-level kb CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

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
from kb_creator.query import run_query


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

    query_parser = subparsers.add_parser("query", help="Materialize a markdown query output")
    query_parser.add_argument("kb_root", type=Path)
    query_parser.add_argument("--question", required=True)
    query_parser.add_argument("--limit", type=int, default=5)
    query_parser.add_argument("--update-registry", action="store_true")

    registry_parser = subparsers.add_parser("registry", help="Build the KB registry")
    registry_parser.add_argument("kb_root", type=Path)

    status_parser = subparsers.add_parser("status", help="Show KB repository status")
    status_parser.add_argument("kb_root", type=Path)

    args = parser.parse_args()

    if args.command == "init":
        result = init_kb(args.kb_root)
    elif args.command == "ingest":
        if not args.source_dir.is_dir():
            fail("kb_ingest", f"Source directory not found: {args.source_dir}")
        result = ingest_kb(args.kb_root, args.source_dir, enhance_tables=args.enhance_tables)
    elif args.command == "compile":
        result = compile_kb(args.kb_root, force=args.force)
    elif args.command == "link":
        result = link_kb(args.kb_root, mode=args.mode, dry_run=args.dry_run)
    elif args.command == "summarize":
        result = summarize_kb(args.kb_root, extract=args.extract, inject_path=args.inject, fmt=args.fmt)
    elif args.command == "health":
        result = run_health_checks(args.kb_root)
    elif args.command == "query":
        result = run_query(args.kb_root, args.question, limit=args.limit, update_registry=args.update_registry)
    elif args.command == "registry":
        result = registry_kb(args.kb_root)
    elif args.command == "status":
        result = status_kb(args.kb_root)
    else:
        fail("kb", "missing subcommand")
        return

    result.emit()
