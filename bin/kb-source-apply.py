#!/usr/bin/env python3
"""CLI wrapper for deterministic source-layout patch application."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.contracts import fail
from kb_creator.source_patch import apply_layout_patches, validate_patch_queue


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and apply source layout patches.")
    parser.add_argument("source_dir", type=Path, help="Directory containing chapter markdown files")
    parser.add_argument("--queue", type=Path, default=None, help="Suggested patch queue JSON")
    parser.add_argument("--candidates", type=Path, default=None, help="layout_candidates.json path")
    parser.add_argument("--overrides", type=Path, default=None, help="Approved overrides JSON path")
    parser.add_argument("--artifacts-dir", type=Path, default=None, help="Directory to persist apply artifacts")
    parser.add_argument("--state-path", type=Path, default=None, help="Optional .kb-state.json path to update")
    parser.add_argument("--approve-all", action="store_true", help="Approve every valid queue item")
    parser.add_argument("--min-confidence", type=float, default=None, help="Auto-approve patches at or above this confidence")
    parser.add_argument("--validate-only", action="store_true", help="Validate queue schema without applying")
    args = parser.parse_args()

    if not args.source_dir.is_dir():
        fail("source_patch_apply", f"Not a directory: {args.source_dir}")

    if args.validate_only:
        if args.queue is None:
            fail("source_patch_validate", "--validate-only requires --queue")
        result = validate_patch_queue(args.queue, candidates_path=args.candidates)
        result.emit()
        return

    result = apply_layout_patches(
        args.source_dir,
        queue_path=args.queue,
        candidates_path=args.candidates,
        overrides_path=args.overrides,
        artifacts_dir=args.artifacts_dir,
        state_path=args.state_path,
        approve_all=args.approve_all,
        min_confidence=args.min_confidence,
    )
    result.emit()


if __name__ == "__main__":
    main()
