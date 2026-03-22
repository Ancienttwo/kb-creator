#!/usr/bin/env python3
"""CLI wrapper for kb-creator summary extractor/injector."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.contracts import fail
from kb_creator.summarizer import extract, inject


def main() -> None:
    parser = argparse.ArgumentParser(description="Summary extraction and injection")
    parser.add_argument("vault_dir", type=Path, help="Path to Obsidian vault root")
    parser.add_argument("--extract", action="store_true", help="Extract summary candidates")
    parser.add_argument("--inject", type=Path, default=None, metavar="SUMMARIES_JSON",
                        help="Inject summaries from JSON file")
    parser.add_argument("--format", choices=["callout", "frontmatter"], default="callout",
                        dest="fmt", help="Injection format")
    parser.add_argument("--artifacts-dir", type=Path, default=None)
    args = parser.parse_args()

    if not args.vault_dir.is_dir():
        fail("summary", f"Not a directory: {args.vault_dir}")

    if args.extract:
        result = extract(args.vault_dir, artifacts_dir=args.artifacts_dir)
    elif args.inject:
        result = inject(args.vault_dir, args.inject, fmt=args.fmt)
    else:
        fail("summary", "Must specify --extract or --inject <path>")
        return

    result.emit()


if __name__ == "__main__":
    main()
