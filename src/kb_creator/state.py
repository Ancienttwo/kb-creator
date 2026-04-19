"""State management for incremental kb-creator sessions.

The .kb-state.json file tracks both legacy KB-root state and the newer
two-tier vault state used by ``build-book`` and root distillation flows.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from dataclasses import dataclass, field


STATE_FILENAME = ".kb-state.json"
SOURCE_LAYER_STAGES = (
    "split_complete",
    "layout_qa_complete",
    "patches_pending",
    "patches_applied",
    "qa_verified",
)


def _default_source_layer_status() -> dict[str, bool]:
    return {stage: False for stage in SOURCE_LAYER_STAGES}


BOOK_STAGE_NAMES = (
    "extract_complete",
    "split_complete",
    "layout_qa_complete",
    "patches_applied",
    "book_compiled",
    "distill_ready",
    "root_promotion_applied",
)


def _default_book_stages() -> dict[str, bool]:
    return {stage: False for stage in BOOK_STAGE_NAMES}


@dataclass
class KBState:
    """Top-level session state."""

    version: int = 2
    kb_root: str = ""
    source_dir: str = ""
    output_dir: str = ""
    output_mode: str = "local"  # local | vault
    domain: str = ""
    language: str = ""
    phase: str = "init"  # init | ingest | compile | link | summary | health | query | registry | view | done
    grouping_strategy: str = "auto"
    split_config: dict[str, Any] = field(default_factory=dict)
    link_mode: str = "both"
    summary_mode: str = "extract"
    categories: dict[str, list[str]] = field(default_factory=dict)
    raw_dir: str = "raw"
    wiki_dir: str = "wiki"
    outputs_dir: str = "outputs"
    artifacts_dir: str = ".kb-artifacts"
    files: dict[str, dict[str, Any]] = field(default_factory=dict)
    provenance: dict[str, list[str]] = field(default_factory=dict)
    last_health_report: str = ""
    last_query_output: str = ""
    last_query_sources: list[str] = field(default_factory=list)
    last_filed_query: str = ""
    last_compile_workset: str = ""
    last_log_entry: str = ""
    source_layer_status: dict[str, bool] = field(default_factory=_default_source_layer_status)
    books: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_root_promotion_workset: str = ""
    last_root_promotion_report: str = ""
    last_permit_path: str = ""
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
        self.ensure_source_layer_status()
        self.ensure_books()
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

    def mark_ingested(
        self,
        source: str,
        raw_path: str,
        source_hash: str,
        category: str = "",
    ) -> None:
        """Record normalized raw content for a source file."""
        entry = self.files.get(source, {"status": "pending"})
        entry.update({
            "status": "ingested",
            "raw_path": raw_path,
            "hash": source_hash,
            "category": category,
            "dirty": True,
        })
        self.files[source] = entry

    def mark_compiled(
        self,
        source: str,
        source_hash: str,
        artifacts: list[str],
    ) -> None:
        """Record compile outputs produced from a source file."""
        entry = self.files.get(source, {"status": "pending"})
        entry.update({
            "status": "compiled",
            "hash": source_hash,
            "artifacts": artifacts,
            "dirty": False,
        })
        self.files[source] = entry
        self.provenance[source] = artifacts

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

    def ensure_source_layer_status(self) -> dict[str, bool]:
        """Backfill source-layer status flags introduced after v2."""
        current = dict(self.source_layer_status or {})
        for stage in SOURCE_LAYER_STAGES:
            current.setdefault(stage, False)
        self.source_layer_status = current
        return current

    def mark_source_layer_stage(self, stage: str, value: bool = True) -> None:
        """Update one source-layer stage flag."""
        if stage not in SOURCE_LAYER_STAGES:
            raise ValueError(f"unknown source-layer stage: {stage}")
        self.ensure_source_layer_status()
        self.source_layer_status[stage] = value

    def update_source_layer_status(self, **updates: bool) -> None:
        """Apply multiple source-layer status updates at once."""
        self.ensure_source_layer_status()
        for stage, value in updates.items():
            self.mark_source_layer_stage(stage, value)

    def ensure_books(self) -> dict[str, dict[str, Any]]:
        """Backfill the two-tier book state structure."""
        current = dict(self.books or {})
        for book_slug, payload in list(current.items()):
            if not isinstance(payload, dict):
                payload = {}
                current[book_slug] = payload
            stages = payload.get("stages") or {}
            if not isinstance(stages, dict):
                stages = {}
            for stage in BOOK_STAGE_NAMES:
                stages.setdefault(stage, False)
            payload["stages"] = stages
            payload.setdefault("qa_candidate_count", 0)
            payload.setdefault("review_needed", False)
            payload.setdefault("promotion_blocked", False)
            payload.setdefault("tombstoned", False)
            payload.setdefault("root_notes", [])
        self.books = current
        return current

    def upsert_book(self, book_slug: str, **updates: Any) -> dict[str, Any]:
        """Create or update one tracked book entry."""
        self.ensure_books()
        book = dict(self.books.get(book_slug) or {})
        stages = dict(book.get("stages") or {})
        for stage in BOOK_STAGE_NAMES:
            stages.setdefault(stage, False)
        if "stages" in updates:
            for stage, value in dict(updates.pop("stages") or {}).items():
                if stage in BOOK_STAGE_NAMES:
                    stages[stage] = bool(value)
        book["stages"] = stages
        for key, value in updates.items():
            book[key] = value
        book.setdefault("root_notes", [])
        book.setdefault("qa_candidate_count", 0)
        book.setdefault("review_needed", False)
        book.setdefault("promotion_blocked", False)
        book.setdefault("tombstoned", False)
        book["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.books[book_slug] = book
        return book

    def mark_book_stage(self, book_slug: str, stage: str, value: bool = True) -> dict[str, Any]:
        """Update one stage for a tracked book."""
        if stage not in BOOK_STAGE_NAMES:
            raise ValueError(f"unknown book stage: {stage}")
        book = self.upsert_book(book_slug)
        book["stages"][stage] = value
        self.books[book_slug] = book
        return book
