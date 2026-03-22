#!/usr/bin/env python3
"""CLI wrapper for the kb-creator document splitter.

Usage:
    ./.venv/bin/python bin/kb-split.py <input.md|batch.json> <output_dir> --config <split-config.json> [--artifacts-dir <path>]

stdout is JSON only.  Logs go to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure the project source is importable when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.contracts import Result, fail, log  # noqa: E402
from kb_creator.splitter import split_batch, split_file  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split markdown documents into chapter-level notes.",
    )
    parser.add_argument(
        "input",
        help="Path to a single .md file or a batch manifest .json",
    )
    parser.add_argument(
        "output_dir",
        help="Directory to write split output files",
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to split configuration JSON",
    )
    parser.add_argument(
        "--artifacts-dir",
        default=None,
        help="Directory to persist intermediate artifacts",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)

    input_path = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()
    config_path = Path(args.config).resolve()
    artifacts_dir = Path(args.artifacts_dir).resolve() if args.artifacts_dir else None

    # --- Load config -------------------------------------------------------
    if not config_path.exists():
        fail("kb-split", f"config file not found: {config_path}", {"config": str(config_path)})
        return  # fail() calls sys.exit, but keep for clarity

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        fail("kb-split", f"failed to read config: {exc}", {"config": str(config_path)})
        return

    # --- Dispatch: single file vs. batch -----------------------------------
    if not input_path.exists():
        fail("kb-split", f"input not found: {input_path}", {"input": str(input_path)})
        return

    if input_path.suffix == ".json":
        log(f"batch mode: {input_path.name}")
        result = split_batch(input_path, output_dir, config, artifacts_dir=artifacts_dir)
    else:
        log(f"single file mode: {input_path.name}")
        result = split_file(input_path, output_dir, config)

    result.emit()


if __name__ == "__main__":
    main()
