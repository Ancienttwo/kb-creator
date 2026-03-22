"""State management for incremental kb-creator sessions.

The .kb-state.json file tracks task parameters, per-file status,
and current phase so that an interrupted session can resume.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from dataclasses import dataclass, field


STATE_FILENAME = ".kb-state.json"


@dataclass
class KBState:
    """Top-level session state."""

    version: int = 1
    source_dir: str = ""
    output_dir: str = ""
    output_mode: str = "local"  # local | vault
    domain: str = ""
    language: str = ""
    phase: str = "init"  # init | scan | convert | split | link | summary | registry | view | done
    grouping_strategy: str = "auto"
    split_config: dict[str, Any] = field(default_factory=dict)
    link_mode: str = "both"
    summary_mode: str = "extract"
    categories: dict[str, list[str]] = field(default_factory=dict)
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def load(cls, path: Path) -> KBState | None:
        """Load state from disk. Returns None if not found."""
        state_file = path / STATE_FILENAME if path.is_dir() else path
        if not state_file.exists():
            return None
        data = json.loads(state_file.read_text(encoding="utf-8"))
        state = cls()
        for k, v in data.items():
            if hasattr(state, k):
                setattr(state, k, v)
        return state

    def save(self, path: Path) -> Path:
        """Persist state to disk. Returns the state file path."""
        state_file = path / STATE_FILENAME if path.is_dir() else path
        self.updated_at = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = self.updated_at
        data = {
            k: v for k, v in self.__dict__.items()
            if not k.startswith("_")
        }
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return state_file

    def update_file(self, source: str, status: str, notes: list[str] | None = None, error: str | None = None) -> None:
        """Update a file's pipeline status."""
        entry = self.files.get(source, {"status": "pending"})
        entry["status"] = status
        if notes is not None:
            entry["notes"] = notes
        if error is not None:
            entry["error"] = error
        self.files[source] = entry

    def files_in_status(self, status: str) -> list[str]:
        """Return source files matching a given status."""
        return [k for k, v in self.files.items() if v.get("status") == status]

    def progress_summary(self) -> dict[str, int]:
        """Return counts by status."""
        counts: dict[str, int] = {}
        for v in self.files.values():
            s = v.get("status", "unknown")
            counts[s] = counts.get(s, 0) + 1
        return counts
