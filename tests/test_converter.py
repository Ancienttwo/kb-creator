"""Test converter dependency checks and markitdown detection."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.converter import check_deps


def test_check_deps_returns_ok_when_all_ready():
    """When markitdown is importable, ok should be True."""
    result = check_deps()
    # In our venv markitdown IS installed
    assert result.ok is True
    assert result.outputs["markitdown"] is True
    assert len(result.outputs["missing"]) == 0


def test_check_deps_returns_false_when_markitdown_missing():
    """When markitdown is NOT importable, ok must be False."""
    with patch("kb_creator.converter._has_markitdown", return_value=False):
        result = check_deps()
    assert result.ok is False
    assert "markitdown" in result.outputs["missing"]


def test_check_deps_contract_fields():
    """Result must contain ready, missing, available fields."""
    result = check_deps()
    assert "ready" in result.outputs
    assert "missing" in result.outputs
    assert "available" in result.outputs
