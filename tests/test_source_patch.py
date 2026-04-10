"""Tests for deterministic source-layout patch application."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.source_patch import apply_layout_patches, validate_patch_queue
from kb_creator.source_qa import run_layout_qa
from kb_creator.state import KBState


ROOT = Path(__file__).resolve().parent.parent


def _load_candidates(result) -> list[dict]:
    payload = json.loads(Path(result.artifacts["layout_candidates"]).read_text(encoding="utf-8"))
    return payload["candidates"]


def test_validate_patch_queue_rejects_invalid_operation(tmp_path):
    source_root = tmp_path / "book"
    source_root.mkdir()
    (source_root / "table.md").write_text(
        "# 察用神\n\n木  火  土\n甲  乙  丙\n财  官  父\n",
        encoding="utf-8",
    )
    qa_result = run_layout_qa(source_root)
    candidates_path = Path(qa_result.artifacts["layout_candidates"])
    candidate = _load_candidates(qa_result)[0]

    queue_path = tmp_path / "layout_patch_queue.json"
    queue_path.write_text(json.dumps([{
        "candidate_id": candidate["candidate_id"],
        "operation": "rewrite_everything",
        "payload": {"replacement": "ignored"},
        "rationale": "bad op",
        "confidence": 0.9,
    }], ensure_ascii=False, indent=2), encoding="utf-8")

    result = validate_patch_queue(queue_path, candidates_path=candidates_path)
    assert result.ok is False
    assert result.outputs["invalid_count"] == 1


def test_apply_layout_patches_is_idempotent(tmp_path):
    source_root = tmp_path / "book"
    source_root.mkdir()
    chapter = source_root / "table.md"
    chapter.write_text(
        "# 察用神\n\n木  火  土\n甲  乙  丙\n财  官  父\n",
        encoding="utf-8",
    )
    state = KBState(kb_root=str(source_root))
    state.save(source_root)

    qa_result = run_layout_qa(source_root)
    candidates = _load_candidates(qa_result)
    table_candidate = next(item for item in candidates if item["risk_type"] == "table_fragment")
    queue_path = tmp_path / "layout_patch_queue.json"
    queue_path.write_text(json.dumps([{
        "candidate_id": table_candidate["candidate_id"],
        "operation": "replace_with_table",
        "payload": {
            "header": ["木", "火", "土"],
            "rows": [["甲", "乙", "丙"], ["财", "官", "父"]],
        },
        "rationale": "restore stable table layout",
        "confidence": 0.94,
    }], ensure_ascii=False, indent=2), encoding="utf-8")

    first = apply_layout_patches(
        source_root,
        queue_path=queue_path,
        candidates_path=Path(qa_result.artifacts["layout_candidates"]),
        approve_all=True,
    )
    second = apply_layout_patches(source_root)

    assert first.ok
    assert first.outputs["applied_count"] == 1
    assert second.ok
    assert second.outputs["applied_count"] == 0
    assert "| 木 | 火 | 土 |" in chapter.read_text(encoding="utf-8")

    loaded = KBState.load(source_root)
    assert loaded is not None
    assert loaded.source_layer_status["split_complete"] is True
    assert loaded.source_layer_status["patches_applied"] is True


def test_apply_layout_patches_can_wrap_chart_block(tmp_path):
    source_root = tmp_path / "book"
    source_root.mkdir()
    chapter = source_root / "chart.md"
    chapter.write_text(
        "# 占验一\n\n贵 后 阴 玄\n子 丑 寅 卯\n龙 勾 合 朱\n巳 午 未 申\n",
        encoding="utf-8",
    )
    qa_result = run_layout_qa(source_root)
    candidates = _load_candidates(qa_result)
    chart_candidate = next(item for item in candidates if item["risk_type"] == "chart_block")
    queue_path = tmp_path / "layout_patch_queue.json"
    queue_path.write_text(json.dumps([{
        "candidate_id": chart_candidate["candidate_id"],
        "operation": "wrap_code_block",
        "payload": {
            "language": "text",
            "content": chart_candidate["source_excerpt"],
        },
        "rationale": "preserve chart alignment",
        "confidence": 0.91,
    }], ensure_ascii=False, indent=2), encoding="utf-8")

    result = apply_layout_patches(
        source_root,
        queue_path=queue_path,
        candidates_path=Path(qa_result.artifacts["layout_candidates"]),
        approve_all=True,
    )
    assert result.ok
    content = chapter.read_text(encoding="utf-8")
    assert "```text" in content
    assert "贵 后 阴 玄" in content


def test_apply_layout_patches_can_drop_noise_lines_without_dropping_body(tmp_path):
    source_root = tmp_path / "book"
    source_root.mkdir()
    chapter = source_root / "noise.md"
    chapter.write_text("# 标题\n\n12\n正文开始。\n正文续行。\n", encoding="utf-8")

    qa_result = run_layout_qa(source_root)
    candidates = _load_candidates(qa_result)
    noise_candidate = next(item for item in candidates if item["risk_type"] == "running_header_noise")
    queue_path = tmp_path / "layout_patch_queue.json"
    queue_path.write_text(json.dumps([{
        "candidate_id": noise_candidate["candidate_id"],
        "operation": "drop_noise_lines",
        "payload": {"lines": ["12"]},
        "rationale": "drop stray page marker",
        "confidence": 0.88,
    }], ensure_ascii=False, indent=2), encoding="utf-8")

    result = apply_layout_patches(
        source_root,
        queue_path=queue_path,
        candidates_path=Path(qa_result.artifacts["layout_candidates"]),
        approve_all=True,
    )
    assert result.ok
    content = chapter.read_text(encoding="utf-8")
    assert "12" not in content
    assert "正文开始。" in content
    assert "正文续行。" in content


def test_source_patch_cli_validate_only_emits_json(tmp_path):
    source_root = tmp_path / "book"
    source_root.mkdir()
    (source_root / "table.md").write_text(
        "# 察用神\n\n木  火  土\n甲  乙  丙\n财  官  父\n",
        encoding="utf-8",
    )
    qa_result = run_layout_qa(source_root)
    candidate = _load_candidates(qa_result)[0]
    queue_path = tmp_path / "layout_patch_queue.json"
    queue_path.write_text(json.dumps([{
        "candidate_id": candidate["candidate_id"],
        "operation": "replace_block",
        "payload": {"replacement": candidate["source_excerpt"]},
        "rationale": "noop validation",
        "confidence": 0.8,
    }], ensure_ascii=False, indent=2), encoding="utf-8")

    proc = subprocess.run(
        [
            sys.executable,
            "bin/kb-source-apply.py",
            str(source_root),
            "--queue",
            str(queue_path),
            "--candidates",
            str(Path(qa_result.artifacts["layout_candidates"])),
            "--validate-only",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(proc.stdout)
    assert payload["action"] == "source_patch_validate"
    assert payload["ok"] is True


def test_apply_layout_patches_reports_custom_overrides_path(tmp_path):
    source_root = tmp_path / "book"
    source_root.mkdir()
    (source_root / "table.md").write_text(
        "# 察用神\n\n木  火  土\n甲  乙  丙\n财  官  父\n",
        encoding="utf-8",
    )
    qa_result = run_layout_qa(source_root)
    candidate = next(item for item in _load_candidates(qa_result) if item["risk_type"] == "table_fragment")
    queue_path = tmp_path / "layout_patch_queue.json"
    queue_path.write_text(json.dumps([{
        "candidate_id": candidate["candidate_id"],
        "operation": "replace_block",
        "payload": {"replacement": candidate["source_excerpt"]},
        "rationale": "track path",
        "confidence": 0.8,
    }], ensure_ascii=False, indent=2), encoding="utf-8")
    overrides_path = tmp_path / "custom" / "layout_overrides.json"

    result = apply_layout_patches(
        source_root,
        queue_path=queue_path,
        candidates_path=Path(qa_result.artifacts["layout_candidates"]),
        overrides_path=overrides_path,
        approve_all=True,
    )

    assert result.ok
    assert result.outputs["overrides_path"] == str(overrides_path.resolve())
