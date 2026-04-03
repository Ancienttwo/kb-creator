"""Tests for the top-level kb CLI and repository workflow."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.kb import compile_kb, ingest_kb, init_kb, status_kb
from kb_creator.state import KBState


def test_init_kb_creates_layout(tmp_path):
    kb_root = tmp_path / "kb"
    result = init_kb(kb_root)

    assert result.ok
    assert (kb_root / "raw" / "sources").is_dir()
    assert (kb_root / "wiki" / "summaries").is_dir()
    assert (kb_root / "wiki" / "concepts").is_dir()
    assert (kb_root / "outputs" / "qa").is_dir()
    assert (kb_root / ".kb-artifacts").is_dir()

    state = KBState.load(kb_root)
    assert state is not None
    assert state.kb_root == str(kb_root.resolve())


def test_ingest_compile_and_status(tmp_path):
    kb_root = tmp_path / "kb"
    src_root = tmp_path / "sources"
    (src_root / "research").mkdir(parents=True)
    (src_root / "research" / "llm-notes.md").write_text(
        "# LLM Knowledge Bases\n\n## Data ingest\n\nUseful notes.\n\n## Output\n\nArtifacts.\n",
        encoding="utf-8",
    )

    init_kb(kb_root)
    ingest = ingest_kb(kb_root, src_root)
    compile_result = compile_kb(kb_root)
    status = status_kb(kb_root)

    assert ingest.ok
    assert ingest.outputs["ingested"] == 1
    assert compile_result.ok
    assert compile_result.outputs["updated_summaries"] == 1
    assert status.outputs["raw_sources"] == 1
    assert status.outputs["wiki_notes"] >= 4

    raw_copy = kb_root / "raw" / "sources" / "research" / "llm-notes.md"
    assert raw_copy.exists()
    summary_files = list((kb_root / "wiki" / "summaries" / "research").glob("*.md"))
    assert len(summary_files) == 1
    assert list((kb_root / "wiki" / "concepts").glob("*.md"))


def test_top_level_cli_emits_json(tmp_path):
    kb_root = tmp_path / "kb"
    proc = subprocess.run(
        [sys.executable, "bin/kb.py", "init", str(kb_root)],
        cwd=Path(__file__).resolve().parent.parent,
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["action"] == "kb_init"
    assert payload["outputs"]["layout"]["raw"] == "raw"
