#!/usr/bin/env python3
"""CLI wrapper for source-layout risk detection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.contracts import fail
from kb_creator.source_qa import run_layout_qa


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect layout-risk candidates in source markdown.")
    parser.add_argument("source_dir", type=Path, help="Directory containing chapter markdown files")
    parser.add_argument("--artifacts-dir", type=Path, default=None, help="Directory to persist layout artifacts")
    parser.add_argument("--state-path", type=Path, default=None, help="Optional .kb-state.json path to update")
    args = parser.parse_args()

    if not args.source_dir.is_dir():
        fail("source_layout_qa", f"Not a directory: {args.source_dir}")

    result = run_layout_qa(
        args.source_dir,
        artifacts_dir=args.artifacts_dir,
        state_path=args.state_path,
    )
    result.emit()


if __name__ == "__main__":
    main()
