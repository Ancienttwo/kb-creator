"""Tests for product-facing positioning and Skill dependency docs."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_readme_is_skill_first():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Skill-first knowledge-base builder" in readme
    assert "CLI-first knowledge-base builder" not in readme
    assert "obsidian-markdown" in readme
    assert "build-book" in readme
    assert "distill-to-root" in readme


def test_skill_declares_external_dependency():
    skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "Primary product surface" in skill
    assert "obsidian-markdown" in skill
    assert "dependency error" in skill
    assert "CLI-first" not in skill


def test_spec_is_skill_first():
    spec = (ROOT / "docs" / "spec.md").read_text(encoding="utf-8")
    assert "Skill-first" in spec
    assert "CLI-first" not in spec
    assert "obsidian_contract_violations" in spec
    assert "two-tier vault model" in spec
