"""Test state management and recovery."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.state import KBState


def test_save_and_load(tmp_path):
    state = KBState(
        source_dir="/test/source",
        output_dir="/test/output",
        phase="convert",
        domain="compliance",
    )
    state.update_file("doc1.pdf", "converted", notes=["ch1.md", "ch2.md"])
    state.update_file("doc2.docx", "pending")

    state.save(tmp_path)
    loaded = KBState.load(tmp_path)

    assert loaded is not None
    assert loaded.source_dir == "/test/source"
    assert loaded.phase == "convert"
    assert loaded.files["doc1.pdf"]["status"] == "converted"
    assert loaded.files["doc1.pdf"]["notes"] == ["ch1.md", "ch2.md"]


def test_load_nonexistent(tmp_path):
    assert KBState.load(tmp_path) is None


def test_progress_summary(tmp_path):
    state = KBState()
    state.update_file("a.pdf", "converted")
    state.update_file("b.pdf", "converted")
    state.update_file("c.pdf", "pending")
    state.update_file("d.pdf", "error", error="conversion failed")

    summary = state.progress_summary()
    assert summary == {"converted": 2, "pending": 1, "error": 1}


def test_files_in_status():
    state = KBState()
    state.update_file("a.pdf", "split")
    state.update_file("b.pdf", "converted")
    state.update_file("c.pdf", "split")

    assert set(state.files_in_status("split")) == {"a.pdf", "c.pdf"}
    assert state.files_in_status("converted") == ["b.pdf"]


def test_state_timestamps(tmp_path):
    state = KBState(source_dir="/test")
    state.save(tmp_path)

    assert state.created_at != ""
    assert state.updated_at != ""

    raw = json.loads((tmp_path / ".kb-state.json").read_text())
    assert "T" in raw["created_at"]  # ISO format
