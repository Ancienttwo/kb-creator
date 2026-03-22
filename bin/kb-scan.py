#!/usr/bin/env python3
"""CLI wrapper for the kb-creator source directory scanner.

Usage:
    ./.venv/bin/python bin/kb-scan.py <source_dir> [--artifacts-dir <path>]

Stdout is reserved for the JSON Result; diagnostics go to stderr.
"""

import argparse
import sys
from pathlib import Path

# Ensure the project's src/ is importable when running from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.contracts import Result, log, fail  # noqa: E402
from kb_creator.scanner import scan  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scan a source directory for supported document files.",
    )
    parser.add_argument(
        "source_dir",
        type=Path,
        help="Root directory to scan recursively.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Directory for persisting intermediate artifacts (e.g. scan manifest).",
    )
    args = parser.parse_args()

    source_dir: Path = args.source_dir.resolve()
    artifacts_dir: Path | None = args.artifacts_dir.resolve() if args.artifacts_dir else None

    if not source_dir.exists():
        fail("scan", f"source_dir does not exist: {source_dir}", {"source_dir": str(source_dir)})
        return  # fail() calls sys.exit, but keeps type-checkers happy

    result = scan(source_dir, artifacts_dir)
    result.emit()


if __name__ == "__main__":
    main()
