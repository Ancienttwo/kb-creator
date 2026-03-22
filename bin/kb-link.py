#!/usr/bin/env python3
"""CLI wrapper for kb-creator link engine."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.contracts import fail
from kb_creator.linker import link


def main() -> None:
    parser = argparse.ArgumentParser(description="Wiki-link injection engine")
    parser.add_argument("vault_dir", type=Path, help="Path to Obsidian vault root")
    parser.add_argument("--mode", choices=["structural", "semantic", "both"], default="both")
    parser.add_argument("--dry-run", action="store_true", help="Output patch plan without modifying files")
    parser.add_argument("--artifacts-dir", type=Path, default=None)
    args = parser.parse_args()

    if not args.vault_dir.is_dir():
        fail("link", f"Vault directory not found: {args.vault_dir}", {"vault_dir": str(args.vault_dir)})

    result = link(
        vault_dir=args.vault_dir,
        mode=args.mode,
        dry_run=args.dry_run,
        artifacts_dir=args.artifacts_dir,
    )
    result.emit()


if __name__ == "__main__":
    main()
