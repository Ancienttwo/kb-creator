"""Tests for health, query, and expanded registry behavior."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.health import run_health_checks
from kb_creator.lint import run_lint_checks
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
    compile_kb(kb_root, emit_workset=True)

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
    assert "page_sources" in registry
    assert "source_pages" in registry
    assert "query_outputs" in registry
    assert "log_entries" in registry


def test_query_synthesize_can_file_back_and_update_registry(tmp_path):
    kb_root = tmp_path / "kb"
    src_root = tmp_path / "sources"
    src_root.mkdir()
    (src_root / "obsidian.md").write_text(
        "# Obsidian Workflow\n\n## Knowledge Base\n\nThe wiki stores summaries and concepts.\n\n## Query Notes\n\nQueries can be filed back.\n",
        encoding="utf-8",
    )

    init_kb(kb_root)
    ingest_kb(kb_root, src_root)
    compile_kb(kb_root, emit_workset=True)

    query_result = run_query(
        kb_root,
        "how does query filing work",
        limit=3,
        update_registry=True,
        mode="synthesize",
        file_back=True,
    )
    registry_result = registry_kb(kb_root)
    registry = json.loads(Path(registry_result.artifacts["vault_registry"]).read_text(encoding="utf-8"))

    assert query_result.ok
    assert query_result.outputs["mode"] == "synthesize"
    answer_path = Path(query_result.outputs["answer_path"])
    assert answer_path.exists()
    assert "## Conclusion" in answer_path.read_text(encoding="utf-8")

    filed_back_path = Path(query_result.outputs["filed_back_path"])
    filed_back_index_path = Path(query_result.outputs["filed_back_index_path"])
    assert filed_back_path.exists()
    assert filed_back_index_path.exists()
    assert query_result.outputs["file_back_action"] == "created"
    assert filed_back_path.name.endswith("--v1.md")
    filed_back_content = filed_back_path.read_text(encoding="utf-8")
    assert 'type: "query-note"' in filed_back_content
    assert 'derived_from_query_output:' in filed_back_content
    assert 'version: 1' in filed_back_content
    assert any(entry["path"] == filed_back_path.relative_to(kb_root / "wiki").as_posix() for entry in registry["notes"])
    assert registry["query_outputs"]


def test_query_file_back_merges_identical_repeats(tmp_path):
    kb_root = tmp_path / "kb"
    src_root = tmp_path / "sources"
    src_root.mkdir()
    (src_root / "workflow.md").write_text(
        "# Workflow\n\n## Query Filing\n\nRepeated grounded answers should merge into the latest version.\n",
        encoding="utf-8",
    )

    init_kb(kb_root)
    ingest_kb(kb_root, src_root)
    compile_kb(kb_root, emit_workset=True)

    first = run_query(kb_root, "how do repeated query notes behave", mode="synthesize", file_back=True)
    second = run_query(kb_root, "how do repeated query notes behave", mode="synthesize", file_back=True)

    version_files = sorted((kb_root / "wiki" / "queries").glob("how-do-repeated-query-notes-behave--v*.md"))
    assert first.outputs["file_back_action"] == "created"
    assert second.outputs["file_back_action"] == "merged"
    assert len(version_files) == 1
    merged_content = version_files[0].read_text(encoding="utf-8")
    assert "derived_from_query_outputs:" in merged_content
    assert merged_content.count("outputs/qa/") >= 2


def test_query_file_back_versions_when_grounded_answer_changes(tmp_path):
    kb_root = tmp_path / "kb"
    src_root = tmp_path / "sources"
    src_root.mkdir()
    source_path = src_root / "workflow.md"
    source_path.write_text(
        "# Workflow\n\n## Query Filing\n\nVersion one answer.\n",
        encoding="utf-8",
    )

    init_kb(kb_root)
    ingest_kb(kb_root, src_root)
    compile_kb(kb_root, emit_workset=True)

    first = run_query(kb_root, "how do query note versions behave", mode="synthesize", file_back=True)
    source_path.write_text(
        "# Workflow\n\n## Query Filing\n\nVersion two answer with different grounding.\n",
        encoding="utf-8",
    )
    ingest_kb(kb_root, src_root)
    compile_kb(kb_root, emit_workset=True)
    second = run_query(kb_root, "how do query note versions behave", mode="synthesize", file_back=True)

    version_files = sorted((kb_root / "wiki" / "queries").glob("how-do-query-note-versions-behave--v*.md"))
    history_index = kb_root / "wiki" / "queries" / "how-do-query-note-versions-behave.md"

    assert first.outputs["file_back_action"] == "created"
    assert second.outputs["file_back_action"] == "versioned"
    assert len(version_files) == 2
    assert Path(second.outputs["filed_back_path"]).name.endswith("--v2.md")
    assert history_index.exists()
    assert "Version 2" in history_index.read_text(encoding="utf-8")


def test_lint_reports_candidate_categories(tmp_path):
    kb_root = tmp_path / "kb"
    src_root = tmp_path / "sources"
    src_root.mkdir()
    (src_root / "alpha.md").write_text(
        "# Alpha\n\n## Shared Idea\n\nAlpha says the process is stable.\n",
        encoding="utf-8",
    )
    (src_root / "beta.md").write_text(
        "# Beta\n\n## Shared Idea\n\nBeta says the process is changing.\n",
        encoding="utf-8",
    )

    init_kb(kb_root)
    ingest_kb(kb_root, src_root)
    compile_kb(kb_root, emit_workset=True)

    result = run_lint_checks(kb_root)
    report_path = Path(result.outputs["report_path"])
    report = json.loads(Path(result.artifacts["lint_report"]).read_text(encoding="utf-8"))

    assert result.ok
    assert report_path.exists()
    assert "missing_concept_pages" in report
    assert "stale_pages" in report
    assert "conflict_candidates" in report
    assert "obsidian_contract_violations" in report
    assert "cold_pages" in report
    assert "research_questions" in report


def test_lint_reports_obsidian_contract_violations(tmp_path):
    kb_root = tmp_path / "kb"
    init_kb(kb_root)
    bad_query_dir = kb_root / "wiki" / "queries"
    bad_query_dir.mkdir(parents=True, exist_ok=True)
    bad_page = bad_query_dir / "bad.md"
    bad_page.write_text(
        "---\n"
        'type: "query-note"\n'
        "---\n\n"
        "Broken internal markdown link [Local](notes.md)\n"
        "[[unterminated link\n",
        encoding="utf-8",
    )

    result = run_lint_checks(kb_root)
    report = json.loads(Path(result.artifacts["lint_report"]).read_text(encoding="utf-8"))

    assert result.ok
    assert result.outputs["counts"]["obsidian_contract_violations"] >= 1
    assert any(item["page"] == "wiki/queries/bad.md" for item in report["obsidian_contract_violations"])
