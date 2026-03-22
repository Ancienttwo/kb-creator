"""Test summarizer injection semantics."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.summarizer import inject


def test_inject_no_frontmatter_skipped(tmp_path):
    """Notes without frontmatter should be skipped, not counted as injected."""
    vault = tmp_path / "vault"
    vault.mkdir()

    # Note with NO frontmatter
    note = vault / "bare.md"
    note.write_text("# Just a heading\n\nSome content.\n", encoding="utf-8")
    original_content = note.read_text()

    # Summaries JSON referencing this note
    summaries = tmp_path / "summaries.json"
    summaries.write_text(json.dumps({
        "bare.md": {"summary": "Test summary"}
    }), encoding="utf-8")

    result = inject(vault, summaries, fmt="frontmatter")
    assert result.ok
    assert result.outputs["injected"] == 0
    assert result.outputs["skipped"] == 1

    # File should be UNCHANGED
    assert note.read_text() == original_content


def test_inject_with_frontmatter(tmp_path):
    """Notes with valid frontmatter should get summary injected."""
    vault = tmp_path / "vault"
    vault.mkdir()

    note = vault / "noted.md"
    note.write_text("---\ntitle: Test\n---\n\n# Content\n", encoding="utf-8")

    summaries = tmp_path / "summaries.json"
    summaries.write_text(json.dumps({
        "noted.md": {"summary": "This is a test summary"}
    }), encoding="utf-8")

    result = inject(vault, summaries, fmt="frontmatter")
    assert result.ok
    assert result.outputs["injected"] == 1
    assert result.outputs["skipped"] == 0

    content = note.read_text()
    assert 'summary: "This is a test summary"' in content


def test_inject_callout_format(tmp_path):
    """Callout format should inject > [!tldr] block."""
    vault = tmp_path / "vault"
    vault.mkdir()

    note = vault / "noted.md"
    note.write_text("---\ntitle: Test\n---\n\n# Content\n", encoding="utf-8")

    summaries = tmp_path / "summaries.json"
    summaries.write_text(json.dumps({
        "noted.md": {"summary": "Quick summary here"}
    }), encoding="utf-8")

    result = inject(vault, summaries, fmt="callout")
    assert result.ok
    assert result.outputs["injected"] == 1

    content = note.read_text()
    assert "> [!tldr]" in content
    assert "Quick summary here" in content


def test_inject_no_summary_text_skipped(tmp_path):
    """Entries with empty summary should be skipped."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "empty.md").write_text("---\ntitle: X\n---\n", encoding="utf-8")

    summaries = tmp_path / "summaries.json"
    summaries.write_text(json.dumps({
        "empty.md": {"summary": ""}
    }), encoding="utf-8")

    result = inject(vault, summaries, fmt="callout")
    assert result.outputs["injected"] == 0
    assert result.outputs["skipped"] == 1
