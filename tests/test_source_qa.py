"""Tests for source-layout risk detection."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.source_qa import run_layout_qa
from kb_creator.state import KBState


ROOT = Path(__file__).resolve().parent.parent


def test_run_layout_qa_detects_requested_risk_types(tmp_path):
    source_root = tmp_path / "book"
    source_root.mkdir()
    (source_root / "table.md").write_text(
        "# 察用神\n\n木  火  土\n甲  乙  丙\n财  官  父\n",
        encoding="utf-8",
    )
    (source_root / "chart.md").write_text(
        "# 占验一\n\n贵 后 阴 玄\n子 丑 寅 卯\n龙 勾 合 朱\n巳 午 未 申\n",
        encoding="utf-8",
    )
    (source_root / "relation.md").write_text(
        "# 刑破害\n\n刑\n冲\n破\n害\n",
        encoding="utf-8",
    )
    state = KBState(kb_root=str(source_root))
    state.save(source_root)

    result = run_layout_qa(source_root)
    assert result.ok
    assert result.outputs["candidate_count"] >= 3
    risk_types = {candidate["risk_type"] for candidate in result.outputs["top_candidates"]}
    payload = json.loads(Path(result.artifacts["layout_candidates"]).read_text(encoding="utf-8"))
    risk_types.update(candidate["risk_type"] for candidate in payload["candidates"])
    assert {"table_fragment", "chart_block", "short_column_relation"} <= risk_types

    loaded = KBState.load(source_root)
    assert loaded is not None
    assert loaded.source_layer_status["split_complete"] is True
    assert loaded.source_layer_status["layout_qa_complete"] is True
    assert loaded.source_layer_status["patches_pending"] is True
    assert loaded.source_layer_status["qa_verified"] is False


def test_source_qa_cli_emits_json_only(tmp_path):
    source_root = tmp_path / "book"
    source_root.mkdir()
    (source_root / "noise.md").write_text("# 标题\n\n12\n正文开始。\n", encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, "bin/kb-source-qa.py", str(source_root)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["action"] == "source_layout_qa"
