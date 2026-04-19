"""Stable JSON output contracts for all kb-creator CLI tools.

Every CLI writes exactly one JSON object to stdout.
Logs and diagnostics go to stderr.
Exit code 0 = success (including partial/needs-action); non-zero = unrecoverable failure.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Result:
    """Universal CLI output contract."""

    ok: bool
    action: str
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    artifacts: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    def emit(self) -> None:
        """Write JSON to stdout and exit with appropriate code."""
        sys.stdout.write(self.to_json())
        sys.stdout.write("\n")
        sys.exit(0 if self.ok else 1)

    def save_artifact(self, name: str, data: Any, artifacts_dir: Path) -> None:
        """Persist an intermediate artifact to disk and register it."""
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        path = artifacts_dir / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.artifacts[name] = str(path)


def log(msg: str) -> None:
    """Write diagnostic message to stderr (never stdout)."""
    sys.stderr.write(f"[kb-creator] {msg}\n")


def fail(action: str, error: str, inputs: dict[str, Any] | None = None) -> None:
    """Emit a failure result and exit 1."""
    Result(
        ok=False,
        action=action,
        inputs=inputs or {},
        errors=[error],
    ).emit()
