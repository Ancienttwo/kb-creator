#!/usr/bin/env python3
"""CLI wrapper for kb-creator vault registry generator."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.contracts import fail
from kb_creator.registry import build_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Vault registry generator")
    parser.add_argument("vault_dir", type=Path, help="Path to Obsidian vault root")
    parser.add_argument("--artifacts-dir", type=Path, default=None)
    args = parser.parse_args()

    if not args.vault_dir.is_dir():
        fail("registry", f"Not a directory: {args.vault_dir}")

    result = build_registry(args.vault_dir, artifacts_dir=args.artifacts_dir)
    result.emit()


if __name__ == "__main__":
    main()
