#!/usr/bin/env python3
"""Top-level CLI for kb-creator knowledge-base repositories."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.cli import main

if __name__ == "__main__":
    main()
