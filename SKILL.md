---
name: kb-creator
description: |
  CLI-first knowledge base builder for Obsidian-first markdown repos. The primary surface is the
  top-level `kb` CLI: init → ingest → compile → link → health → query → registry/status.
  The Skill is a thin orchestration layer over that CLI for agent workflows.
  Use when asked to "create knowledge base", "build vault from documents", "convert docs to Obsidian",
  "知识库", "文档转换", "建 vault", or "KB from source files".
  Do not use for: single note editing, small-scale summarization, or ad-hoc vault querying without
  repository setup/maintenance.
---

# kb-creator

Thin agent wrapper over the `kb` CLI. The product surface is now the CLI; the Skill chooses commands, batches model work when needed, and preserves the JSON contracts.

## Architecture

- **Top-level CLI (`bin/kb.py` / `kb`)** = product surface for KB repositories.
- **Low-level CLI tools (`bin/kb-*.py`)** = stable stage commands kept for compatibility and fine-grained agent orchestration.
- **Skill (this file)** = orchestration layer that decides which CLI commands to run and when to involve a model.
- **All intermediate artifacts** persist inside the KB root, especially `.kb-artifacts/` and `.kb-state.json`.

## CLI vs Skill

This project is **CLI-first**.

- The **CLI is the source of truth** for product behavior.
- The **Skill teaches an agent how to use the CLI**.
- If a capability can be expressed cleanly as a deterministic `kb` command, prefer the CLI.
- The Skill should only add orchestration that is awkward or impossible to encode in the CLI contract.

Default decision rule:

1. Try the top-level `kb` CLI first.
2. Use low-level `kb-*` commands only when the top-level command is too coarse.
3. Use Skill-only logic only for model-dependent orchestration, batching, or policy decisions.

The Skill must not become a second product surface with behavior that drifts away from the CLI.

## Prerequisites

This skill must run with the Python interpreter inside the installed skill directory:

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python --version
```

If `${CLAUDE_SKILL_DIR}/.venv/bin/python` does not exist, stop and repair the skill installation first. Do not fall back to system `python` or `python3`.

Dependencies must be installed into `${CLAUDE_SKILL_DIR}/.venv`.

Run dependency check first:

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-convert.py --check-deps
```

If `ok: false`, install missing tools:
```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python -m pip install markitdown pdfplumber
```

Re-check until `ok: true`.

## Input Parameters

This skill accepts a structured task object. If parameters are provided, use them directly. If missing, ask the user **only the minimum necessary questions**.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `source_dir` | Yes | — | Path to source documents directory |
| `output_dir` | Yes | — | Path to output vault or local directory |
| `output_mode` | No | `local` | `vault` (direct to Obsidian) or `local` |
| `grouping_strategy` | No | `auto` | `auto` (from scan) or `manual` |
| `split_config` | No | auto-detect | Split boundary patterns and thresholds |
| `link_mode` | No | `both` | `structural`, `semantic`, or `both` |
| `summary_mode` | No | `extract` | `extract` (candidates only) or `generate` (model TLDR) |
| `resume` | No | `true` | Check `.kb-state.json` for recovery |

## Preferred Workflow

The Skill should default to the top-level CLI. Treat the CLI as the product API and the Skill as usage guidance for agents.

### Phase 0: Initialize KB

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py init <kb_root>
```

This creates:

- `raw/`
- `wiki/`
- `outputs/`
- `.kb-artifacts/`
- `.kb-state.json`

### Phase 1: Ingest

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py ingest <kb_root> <source_dir>
```

This normalizes source docs into `raw/sources/`.

### Phase 2: Compile

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py compile <kb_root>
```

This incrementally updates:

- `wiki/summaries/`
- `wiki/concepts/`
- `wiki/indexes/`

### Phase 3: Operate

Use as needed:

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py link <kb_root>
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py health <kb_root>
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py query <kb_root> --question "..."
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py registry <kb_root>
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py status <kb_root>
```

## What The Skill Owns

The Skill is allowed to do these things on top of the CLI:

- choose command order and recovery strategy
- decide when to rerun `compile`, `health`, or `registry`
- batch summary generation or other model calls around CLI artifacts
- translate user intent into CLI parameters and follow-up operations
- decide when a low-level `kb-*` command is safer than the top-level command

The Skill should not reimplement the KB repository lifecycle in chat when a `kb` command already exists.

## Low-Level Fallbacks

The old `kb-*` commands are still supported, but they are **fallback tools**, not a second primary workflow.

Use them only when one of these is true:

- the top-level `kb` command is too coarse for the requested operation
- an agent needs stage-by-stage inspection of JSON artifacts
- a model-dependent step must be inserted between low-level stages
- debugging requires isolating a single stage

Preferred fallback commands:

- dependency check:
  ```bash
  ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-convert.py --check-deps
  ```
- source scan:
  ```bash
  ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-scan.py <source_dir> --artifacts-dir <kb_root>/.kb-artifacts
  ```
- precise conversion:
  ```bash
  ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-convert.py <input> <kb_root>/raw/sources --enhance-tables --artifacts-dir <kb_root>/.kb-artifacts
  ```
- precise split:
  ```bash
  ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-split.py <input.md> <kb_root>/wiki --config <split-config.json> --artifacts-dir <kb_root>/.kb-artifacts
  ```
- precise link:
  ```bash
  ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-link.py <kb_root>/wiki --mode both --artifacts-dir <kb_root>/.kb-artifacts
  ```
- summary extract/inject:
  ```bash
  ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-summary.py <kb_root>/wiki --extract --artifacts-dir <kb_root>/.kb-artifacts
  ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-summary.py <kb_root>/wiki --inject <kb_root>/.kb-artifacts/all_summaries.json --format callout
  ```
- registry rebuild:
  ```bash
  ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-registry.py <kb_root> --artifacts-dir <kb_root>/.kb-artifacts
  ```

When using these fallbacks, the Skill should still preserve the CLI-first mental model:

1. low-level commands refine or inspect the main `kb` workflow
2. low-level commands do not define a separate product lifecycle
3. if repeated fallback usage becomes common, that capability should probably graduate into the top-level `kb` CLI

## Error Handling

- CLI exits with code 0 for all recoverable situations (parse JSON `ok` field)
- CLI exits non-zero only for truly unrecoverable failures
- On non-zero exit: report the error and stop the current phase
- On `ok: false` with exit 0: check `errors` and `warnings` arrays, decide whether to continue
- Always update `.kb-state.json` before stopping so the session can resume

## Recovery

If the Skill detects `.kb-state.json` on startup:
1. Read state and report current phase and progress
2. Ask: "Continue from where we left off, or restart?"
3. On continue: skip completed phases, resume from current phase
4. On restart: backup old state file, start fresh

## Reference Documents

Load these lazily (only when the corresponding phase needs them):

- `${CLAUDE_SKILL_DIR}/references/splitting-patterns.md` — Phase 2
- `${CLAUDE_SKILL_DIR}/references/frontmatter-schema.md` — Phase 2
- `${CLAUDE_SKILL_DIR}/references/converter-guide.md` — Phase 0-1
- `${CLAUDE_SKILL_DIR}/references/quality-checks.md` — Phase 1
- `${CLAUDE_SKILL_DIR}/references/obsidian-markdown.md` — Phase 3-5
- `${CLAUDE_SKILL_DIR}/references/obsidian-bases.md` — Phase 5
- `${CLAUDE_SKILL_DIR}/references/vault-architecture.md` — repository layout decisions and wiki output shape
