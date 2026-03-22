#!/usr/bin/env python3
"""CLI wrapper for kb-creator document conversion.

Usage:
    ./.venv/bin/python bin/kb-convert.py <input> <output_dir> [options]

    <input>        Single file path or .json file listing paths
    <output_dir>   Directory for converted Markdown files

Options:
    --check-deps        Only check dependency availability and exit
    --enhance-tables    Use pdfplumber for PDF table enhancement
    --artifacts-dir P   Directory to persist intermediate artifacts

stdout is ONLY JSON.  Logs go to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from repo root: ./.venv/bin/python bin/kb-convert.py ...
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.contracts import Result, fail, log
from kb_creator.converter import check_deps, convert_batch, convert_file


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert documents to Markdown.",
        add_help=True,
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Single file or .json file list to convert",
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        help="Output directory for Markdown files",
    )
    parser.add_argument(
        "--check-deps",
        action="store_true",
        dest="check_deps",
        help="Check dependency availability and exit",
    )
    parser.add_argument(
        "--enhance-tables",
        action="store_true",
        dest="enhance_tables",
        help="Use pdfplumber for PDF table enhancement",
    )
    parser.add_argument(
        "--artifacts-dir",
        dest="artifacts_dir",
        default=None,
        help="Directory to persist intermediate artifacts",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    # --check-deps: standalone mode, no positional args required
    if args.check_deps:
        check_deps().emit()
        return  # emit() calls sys.exit

    # Validate required positional args
    if not args.input:
        fail("convert", "missing required argument: <input>")
        return
    if not args.output_dir:
        fail("convert", "missing required argument: <output_dir>")
        return

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()
    artifacts_dir = Path(args.artifacts_dir).resolve() if args.artifacts_dir else None

    if not input_path.exists():
        fail("convert", f"input not found: {input_path}", {"input": str(input_path)})
        return

    # Determine batch vs. single-file mode
    if input_path.suffix.lower() == ".json":
        log(f"batch mode: reading file list from {input_path}")
        result = convert_batch(
            file_list=input_path,
            output_dir=output_dir,
            enhance_tables=args.enhance_tables,
            artifacts_dir=artifacts_dir,
        )
    else:
        log(f"single file mode: {input_path.name}")
        result = convert_file(
            input_path=input_path,
            output_dir=output_dir,
            enhance_tables=args.enhance_tables,
        )
        # Save artifact in single-file mode too, if requested
        if artifacts_dir:
            result.save_artifact(
                "convert_single_detail",
                {"input": str(input_path), "outputs": result.outputs},
                artifacts_dir,
            )

    result.emit()


if __name__ == "__main__":
    main()
