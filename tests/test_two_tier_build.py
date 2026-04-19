"""Tests for two-tier book build and root distillation workflows."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.build import apply_root_promotion, build_book, distill_to_root, issue_permit, status_vault


ROOT = Path(__file__).resolve().parent.parent


def _env() -> dict[str, str]:
    env = dict(os.environ)
    env["KB_WRITE_PERMIT_KEY"] = "test-write-permit-secret"
    return env


def _write_split_config(path: Path, *, min_lines: int = 1) -> None:
    path.write_text(
        json.dumps({"min_lines": min_lines, "max_lines": 5000}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _run_cli(*args: str, env: dict[str, str] | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "bin/kb.py", *args],
        cwd=ROOT,
        env=env or _env(),
        capture_output=True,
        text=True,
        check=check,
    )


def _clean_book_markdown(title: str, chapter_one: str = "Foundations", chapter_two: str = "Patterns") -> str:
    return (
        f"# {title}\n\n"
        f"## {chapter_one}\n\n"
        "This section explains a long-form concept with enough narrative detail to avoid layout heuristics.\n\n"
        f"## {chapter_two}\n\n"
        "This follow-up section keeps the content paragraph-oriented so the QA stage stays clean and ready.\n"
    )


def _table_book_markdown(title: str) -> str:
    return (
        f"# {title}\n\n"
        "## Table Signals\n\n"
        "木  火  土\n"
        "甲  乙  丙\n"
        "财  官  父\n\n"
        "## Closing Notes\n\n"
        "A short narrative tail keeps the file realistic.\n"
    )


def _issue_permit(monkeypatch: pytest.MonkeyPatch, vault_root: Path, *, scope: str, target: str) -> Path:
    monkeypatch.setenv("KB_WRITE_PERMIT_KEY", "test-write-permit-secret")
    permit = issue_permit(vault_root, scope=scope, target=target)
    assert permit.ok
    return Path(permit.outputs["permit_path"])


def test_build_book_cli_happy_path_creates_book_kb_and_root_workflow(tmp_path):
    vault_root = tmp_path / "vault"
    source_path = tmp_path / "alpha.md"
    source_path.write_text(_clean_book_markdown("Alpha Book"), encoding="utf-8")
    split_config = tmp_path / "split.json"
    _write_split_config(split_config)

    permit_payload = json.loads(
        _run_cli("issue-permit", str(vault_root), "--scope", "build-book", "--target", "alpha-book").stdout
    )
    build_payload = json.loads(
        _run_cli(
            "build-book",
            str(vault_root),
            str(source_path),
            "--permit",
            permit_payload["outputs"]["permit_path"],
            "--split-config",
            str(split_config),
        ).stdout
    )

    assert build_payload["ok"] is True
    assert build_payload["outputs"]["review_needed"] is False
    book_kb_path = vault_root / build_payload["outputs"]["book_kb_path"]
    assert book_kb_path.is_dir()
    assert (vault_root / build_payload["outputs"]["raw_source_path"]).exists()
    assert (vault_root / build_payload["outputs"]["chapter_dir"]).is_dir()

    distill_payload = json.loads(_run_cli("distill-to-root", str(vault_root), str(book_kb_path)).stdout)
    assert distill_payload["ok"] is True
    assert distill_payload["outputs"]["proposal_count"] >= 1

    apply_permit = json.loads(
        _run_cli(
            "issue-permit",
            str(vault_root),
            "--scope",
            "apply-root-promotion",
            "--target",
            build_payload["outputs"]["book_slug"],
        ).stdout
    )
    apply_payload = json.loads(
        _run_cli(
            "apply-root-promotion",
            str(vault_root),
            distill_payload["outputs"]["workset_path"],
            "--permit",
            apply_permit["outputs"]["permit_path"],
        ).stdout
    )
    assert apply_payload["ok"] is True
    assert apply_payload["outputs"]["applied_count"] >= 1
    for rel_path in apply_payload["outputs"]["root_notes"]:
        assert (vault_root / rel_path).exists()
    assert (vault_root / "DISTILLED_ROOT_INDEX.md").exists()

    status_payload = json.loads(_run_cli("status", str(vault_root)).stdout)
    assert status_payload["ok"] is True
    assert status_payload["outputs"]["tracked_books"] == 1
    assert status_payload["outputs"]["ready_books"] == 1
    assert status_payload["outputs"]["books"][0]["stages"]["root_promotion_applied"] is True


def test_build_book_blocks_distill_when_qa_review_needed(tmp_path):
    vault_root = tmp_path / "vault"
    source_path = tmp_path / "table.md"
    source_path.write_text(_table_book_markdown("Table Book"), encoding="utf-8")
    split_config = tmp_path / "split.json"
    _write_split_config(split_config)

    permit_payload = json.loads(
        _run_cli("issue-permit", str(vault_root), "--scope", "build-book", "--target", "table-book").stdout
    )
    build_payload = json.loads(
        _run_cli(
            "build-book",
            str(vault_root),
            str(source_path),
            "--permit",
            permit_payload["outputs"]["permit_path"],
            "--split-config",
            str(split_config),
        ).stdout
    )

    assert build_payload["ok"] is True
    assert build_payload["outputs"]["review_needed"] is True

    proc = _run_cli(
        "distill-to-root",
        str(vault_root),
        str(vault_root / build_payload["outputs"]["book_kb_path"]),
        check=False,
    )
    payload = json.loads(proc.stdout)
    assert proc.returncode == 1
    assert payload["ok"] is False
    assert "review-needed" in payload["errors"][0]


def test_build_book_with_patch_queue_clears_review_needed(monkeypatch: pytest.MonkeyPatch, tmp_path):
    vault_root = tmp_path / "vault"
    source_path = tmp_path / "table.md"
    source_path.write_text(_table_book_markdown("Patched Book"), encoding="utf-8")
    split_config = {"min_lines": 1, "max_lines": 5000}

    first_permit = _issue_permit(monkeypatch, vault_root, scope="build-book", target="patched-book")
    first_build = build_book(vault_root, source_path, permit_path=first_permit, split_config=split_config)
    assert first_build.ok
    assert first_build.outputs["review_needed"] is True

    candidates_path = vault_root / first_build.outputs["layout_candidates_path"]
    candidates = json.loads(candidates_path.read_text(encoding="utf-8"))["candidates"]
    table_candidate = next(item for item in candidates if item["risk_type"] == "table_fragment")
    patch_queue = tmp_path / "queue.json"
    patch_queue.write_text(
        json.dumps(
            [
                {
                    "candidate_id": table_candidate["candidate_id"],
                    "operation": "replace_with_table",
                    "payload": {
                        "header": ["木", "火", "土"],
                        "rows": [["甲", "乙", "丙"], ["财", "官", "父"]],
                    },
                    "rationale": "restore table layout",
                    "confidence": 0.95,
                    "approved": True,
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    second_permit = _issue_permit(monkeypatch, vault_root, scope="build-book", target="patched-book")
    second_build = build_book(
        vault_root,
        source_path,
        permit_path=second_permit,
        split_config=split_config,
        patch_queue_path=patch_queue,
    )

    assert second_build.ok
    assert second_build.outputs["review_needed"] is False
    assert second_build.outputs["qa_candidate_count"] == 0


def test_apply_root_promotion_conflict_fails_closed(monkeypatch: pytest.MonkeyPatch, tmp_path):
    vault_root = tmp_path / "vault"
    split_config = {"min_lines": 1, "max_lines": 5000}

    alpha_source = tmp_path / "alpha.md"
    alpha_source.write_text(_clean_book_markdown("Alpha Book", "Shared Insight", "Alpha Tail"), encoding="utf-8")
    alpha_permit = _issue_permit(monkeypatch, vault_root, scope="build-book", target="alpha-book")
    alpha_build = build_book(vault_root, alpha_source, permit_path=alpha_permit, split_config=split_config)
    alpha_workset = distill_to_root(vault_root, vault_root / alpha_build.outputs["book_kb_path"])
    alpha_apply_permit = _issue_permit(monkeypatch, vault_root, scope="apply-root-promotion", target="alpha-book")
    alpha_apply = apply_root_promotion(
        vault_root,
        vault_root / alpha_workset.outputs["workset_path"],
        permit_path=alpha_apply_permit,
    )
    assert alpha_apply.ok

    beta_source = tmp_path / "beta.md"
    beta_source.write_text(_clean_book_markdown("Beta Book", "Shared Insight", "Beta Tail"), encoding="utf-8")
    beta_permit = _issue_permit(monkeypatch, vault_root, scope="build-book", target="beta-book")
    beta_build = build_book(vault_root, beta_source, permit_path=beta_permit, split_config=split_config)
    beta_workset = distill_to_root(vault_root, vault_root / beta_build.outputs["book_kb_path"])
    beta_apply_permit = _issue_permit(monkeypatch, vault_root, scope="apply-root-promotion", target="beta-book")
    beta_apply = apply_root_promotion(
        vault_root,
        vault_root / beta_workset.outputs["workset_path"],
        permit_path=beta_apply_permit,
    )

    assert beta_apply.ok is False
    assert beta_apply.outputs["conflict_count"] >= 1
    assert "Shared Insight.md" in beta_apply.errors[0]


def test_status_tombstones_deleted_book_and_removes_root_notes(monkeypatch: pytest.MonkeyPatch, tmp_path):
    vault_root = tmp_path / "vault"
    source_path = tmp_path / "alpha.md"
    source_path.write_text(_clean_book_markdown("Alpha Book"), encoding="utf-8")

    build_permit = _issue_permit(monkeypatch, vault_root, scope="build-book", target="alpha-book")
    build_result = build_book(vault_root, source_path, permit_path=build_permit, split_config={"min_lines": 1, "max_lines": 5000})
    workset = distill_to_root(vault_root, vault_root / build_result.outputs["book_kb_path"])
    apply_permit = _issue_permit(monkeypatch, vault_root, scope="apply-root-promotion", target="alpha-book")
    apply_result = apply_root_promotion(vault_root, vault_root / workset.outputs["workset_path"], permit_path=apply_permit)

    promoted_paths = [vault_root / rel for rel in apply_result.outputs["root_notes"]]
    assert all(path.exists() for path in promoted_paths)
    source_path.unlink()

    status = status_vault(vault_root)
    assert status.ok
    assert status.outputs["tombstoned_books"] == 1
    assert status.outputs["books"][0]["tombstoned"] is True
    assert all(not path.exists() for path in promoted_paths)
    assert not (vault_root / build_result.outputs["book_kb_path"]).exists()


def test_build_book_rejects_missing_permit_key(tmp_path):
    vault_root = tmp_path / "vault"
    result = issue_permit(vault_root, scope="build-book", target="alpha-book")
    assert result.ok is False
    assert "KB_WRITE_PERMIT_KEY" in result.errors[0]


def test_apply_root_promotion_rejects_wrong_scope(monkeypatch: pytest.MonkeyPatch, tmp_path):
    vault_root = tmp_path / "vault"
    source_path = tmp_path / "alpha.md"
    source_path.write_text(_clean_book_markdown("Alpha Book"), encoding="utf-8")

    build_permit = _issue_permit(monkeypatch, vault_root, scope="build-book", target="alpha-book")
    build_result = build_book(vault_root, source_path, permit_path=build_permit, split_config={"min_lines": 1, "max_lines": 5000})
    workset = distill_to_root(vault_root, vault_root / build_result.outputs["book_kb_path"])
    wrong_permit = _issue_permit(monkeypatch, vault_root, scope="build-book", target="alpha-book")

    result = apply_root_promotion(vault_root, vault_root / workset.outputs["workset_path"], permit_path=wrong_permit)
    assert result.ok is False
    assert "scope mismatch" in result.errors[0]


def test_apply_root_promotion_rejects_path_escape(monkeypatch: pytest.MonkeyPatch, tmp_path):
    vault_root = tmp_path / "vault"
    source_path = tmp_path / "alpha.md"
    source_path.write_text(_clean_book_markdown("Alpha Book"), encoding="utf-8")

    build_permit = _issue_permit(monkeypatch, vault_root, scope="build-book", target="alpha-book")
    build_result = build_book(vault_root, source_path, permit_path=build_permit, split_config={"min_lines": 1, "max_lines": 5000})
    workset_path = vault_root / distill_to_root(vault_root, vault_root / build_result.outputs["book_kb_path"]).outputs["workset_path"]
    workset = json.loads(workset_path.read_text(encoding="utf-8"))
    workset["proposals"][0]["target_path"] = "../escaped.md"
    workset_path.write_text(json.dumps(workset, ensure_ascii=False, indent=2), encoding="utf-8")

    apply_permit = _issue_permit(monkeypatch, vault_root, scope="apply-root-promotion", target="alpha-book")
    result = apply_root_promotion(vault_root, workset_path, permit_path=apply_permit)

    assert result.ok is False
    assert "escapes vault root" in result.errors[0]
    assert not (vault_root.parent / "escaped.md").exists()
