"""Test JSON contract stability."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.contracts import Result


REQUIRED_FIELDS = {"ok", "action", "inputs", "outputs", "warnings", "errors", "artifacts"}


def test_result_has_all_fields():
    r = Result(ok=True, action="test")
    data = json.loads(r.to_json())
    assert set(data.keys()) == REQUIRED_FIELDS


def test_result_ok_true():
    r = Result(ok=True, action="scan", outputs={"count": 5})
    data = json.loads(r.to_json())
    assert data["ok"] is True
    assert data["action"] == "scan"
    assert data["outputs"]["count"] == 5
    assert data["errors"] == []


def test_result_ok_false():
    r = Result(ok=False, action="convert", errors=["file not found"])
    data = json.loads(r.to_json())
    assert data["ok"] is False
    assert len(data["errors"]) == 1


def test_save_artifact(tmp_path):
    r = Result(ok=True, action="test")
    r.save_artifact("report", {"key": "value"}, tmp_path)
    assert "report" in r.artifacts
    artifact_path = Path(r.artifacts["report"])
    assert artifact_path.exists()
    data = json.loads(artifact_path.read_text())
    assert data["key"] == "value"


def test_unicode_json():
    r = Result(ok=True, action="test", outputs={"名称": "测试条例"})
    text = r.to_json()
    assert "测试条例" in text  # ensure_ascii=False
