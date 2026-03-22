"""Test scanner directory filtering and artifact naming."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.scanner import scan


def test_scan_ignores_venv(tmp_path):
    """Files inside .venv should not be counted."""
    # Create a source dir with real files and a .venv
    src = tmp_path / "project"
    src.mkdir()
    (src / "doc.pdf").write_bytes(b"%PDF-1.4 test")
    (src / "notes.md").write_text("# Notes", encoding="utf-8")

    # Create .venv with files that would match
    venv = src / ".venv" / "lib" / "site-packages" / "pkg"
    venv.mkdir(parents=True)
    (venv / "LICENSE.txt").write_text("MIT License")
    (venv / "data.csv").write_text("a,b\n1,2")

    # Also test node_modules
    nm = src / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    (nm / "readme.md").write_text("# pkg")

    result = scan(src)
    assert result.ok
    assert result.outputs["total_files"] == 2  # only doc.pdf + notes.md


def test_scan_ignores_dot_dirs(tmp_path):
    """Hidden directories (starting with .) should be skipped."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "real.docx").write_bytes(b"PK\x03\x04")

    hidden = src / ".hidden"
    hidden.mkdir()
    (hidden / "secret.txt").write_text("secret")

    result = scan(src)
    assert result.outputs["total_files"] == 1


def test_artifact_name_is_scan_report(tmp_path):
    """Artifact should be named 'scan_report', matching SKILL.md contract."""
    src = tmp_path / "docs"
    src.mkdir()
    (src / "test.pdf").write_bytes(b"%PDF")

    artifacts = tmp_path / "artifacts"
    result = scan(src, artifacts_dir=artifacts)

    assert "scan_report" in result.artifacts
    assert Path(result.artifacts["scan_report"]).name == "scan_report.json"
