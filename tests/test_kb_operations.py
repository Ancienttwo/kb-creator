"""Tests for health, query, and expanded registry behavior."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.health import run_health_checks
from kb_creator.kb import compile_kb, ingest_kb, init_kb, registry_kb
from kb_creator.query import run_query


def test_health_reports_summary_gap_for_uncompiled_raw(tmp_path):
    kb_root = tmp_path / "kb"
    raw_source = kb_root / "raw" / "sources"

    init_kb(kb_root)
    raw_source.mkdir(parents=True, exist_ok=True)
    (raw_source / "draft.md").write_text("# Draft\n\nMissing compile.\n", encoding="utf-8")

    result = run_health_checks(kb_root)

    assert result.ok
    assert result.outputs["counts"]["summary_gaps"] == 1
    assert Path(result.outputs["report_path"]).exists()


def test_query_materializes_output_and_registry_counts_outputs(tmp_path):
    kb_root = tmp_path / "kb"
    src_root = tmp_path / "sources"
    src_root.mkdir()
    (src_root / "obsidian.md").write_text(
        "# Obsidian Workflow\n\n## Knowledge Base\n\nThe wiki stores summaries and concepts.\n",
        encoding="utf-8",
    )

    init_kb(kb_root)
    ingest_kb(kb_root, src_root)
    compile_kb(kb_root)

    query_result = run_query(kb_root, "knowledge base workflow", limit=3, update_registry=True)
    registry_result = registry_kb(kb_root)

    assert query_result.ok
    assert query_result.outputs["source_count"] >= 1
    assert Path(query_result.outputs["answer_path"]).exists()

    registry_path = Path(registry_result.artifacts["vault_registry"])
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    assert registry_result.outputs["total_sources"] == 1
    assert registry_result.outputs["total_outputs"] >= 1
    assert registry["stats"]["total_outputs"] >= 1
    assert registry["notes"]
