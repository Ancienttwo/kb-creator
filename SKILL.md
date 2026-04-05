---
name: kb-creator
description: |
  Skill-first knowledge base builder for Obsidian-first markdown repos. Users install and invoke
  this Skill in natural language; the bundled `kb` CLI is an internal deterministic runtime.
  This Skill explicitly depends on the external `obsidian-markdown` Skill for any phase that
  creates or rewrites wiki pages. Use when asked to "create knowledge base", "build vault from
  documents", "convert docs to Obsidian", "知识库", "文档转换", "建 vault", or "KB from source files".
  Do not use for: single note editing, small-scale summarization, or ad-hoc vault querying without
  repository setup/maintenance.
---

# kb-creator

User-facing product surface for building and maintaining agent-usable KB repos. This Skill owns the workflow. The bundled `kb` CLI is the execution engine that provides deterministic JSON-only contracts.

## Product Boundary

- **Primary product surface** = this Skill.
- **Bundled runtime** = `kb` CLI in this repo.
- **Companion dependency Skill** = external `obsidian-markdown`.
- **Intermediate artifacts** persist inside the KB root, especially `.kb-artifacts/`, `.kb-state.json`, `KB_SCHEMA.md`, `wiki/index.md`, and `wiki/log.md`.

Users should not need CLI knowledge. The Skill translates intent into CLI runs, post-processing, and dependency checks.

## Explicit Skill Dependency

`kb-creator` requires the external `obsidian-markdown` Skill for any phase that creates or mutates Obsidian-flavored wiki pages.

Dependency boundary:

- `kb-creator` owns KB lifecycle, ingestion, compile/lint/query orchestration, provenance, state, and file placement.
- `obsidian-markdown` owns Obsidian syntax correctness for wikilinks, frontmatter shape, callouts, embeds, and note-writing conventions.

Before any wiki-writing phase, verify that the external Skill named `obsidian-markdown` is available to the agent runtime. If it is missing:

- stop compile/query-file-back/lint-fix phases that would write or rewrite wiki pages
- report a clear dependency error: `kb-creator requires the external obsidian-markdown Skill for wiki-writing phases`
- allow scan/ingest-only flows to continue if they only normalize raw sources and do not mutate `wiki/`

Do not treat this as a Python dependency. It is an agent-runtime Skill dependency.

## Runtime Prerequisites

This Skill must run with the Python interpreter inside the installed skill directory:

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

## Recommended User Install Model

1. Install the `kb-creator` Skill.
2. Ensure the external `obsidian-markdown` Skill is also installed as a companion dependency.
3. Use natural-language requests to drive the Skill.
4. Use the CLI only for developer debugging, automation, or contract verification.

## Input Parameters

This Skill accepts a structured task object. If parameters are provided, use them directly. If missing, ask the user only the minimum necessary questions.

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `source_dir` | Yes | — | Path to source documents directory |
| `kb_root` | Yes | — | Path to the KB repository root |
| `link_mode` | No | `both` | `structural`, `semantic`, or `both` |
| `summary_mode` | No | `extract` | `extract` or `generate` |
| `resume` | No | `true` | Check `.kb-state.json` for recovery |

## Skill Workflow

### Phase 0: Verify Runtime And Skill Dependency

1. Verify the bundled Python runtime and package dependencies.
2. Verify the external `obsidian-markdown` Skill is available before any wiki-writing phase.
3. If only ingest/scan work is requested, the external Skill may be absent.
4. If compile/query-file-back/lint-guided rewrite work is requested and the external Skill is absent, stop with the dependency error above.

### Phase 1: Run Deterministic CLI Commands

Use the CLI as the execution engine:

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py init <kb_root>
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py ingest <kb_root> <source_dir>
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py compile <kb_root> --emit-workset
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py health <kb_root>
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py lint <kb_root>
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py query <kb_root> --question "..."
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py registry <kb_root>
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb.py status <kb_root>
```

### Phase 2: Apply Obsidian Writing Contract

When the workflow needs to create or rewrite wiki pages:

- load and follow the external `obsidian-markdown` Skill
- treat it as the governing syntax contract for wikilinks, frontmatter, embeds, callouts, and note layout
- do not emit free-form wiki mutations unless the dependency Skill is active
- use deterministic CLI artifacts (`compile_workset.json`, `lint_report.json`, query outputs) as the source of truth for what to change

### Phase 3: Post-Mutation Validation

After any Skill-driven note changes:

- re-run `kb lint`
- re-run `kb registry`
- update the KB only through managed files and persisted artifacts

## Recovery

If the Skill detects `.kb-state.json` on startup:

1. Read state and report current phase and progress.
2. Re-check that `obsidian-markdown` is available before resuming any wiki-writing phase.
3. On continue: skip completed phases and resume from the current phase.
4. On restart: backup old state file and start fresh.

## Developer / Debug Surface

The CLI remains supported for developer debugging, automation, and contract verification. It is not the recommended end-user interface.

Low-level fallback commands remain available when:

- stage-by-stage inspection of JSON artifacts is required
- debugging requires isolating a single stage
- deterministic pre/post steps are needed around model work

## Reference Materials

Load these lazily when relevant:

- external `obsidian-markdown` Skill — required for wiki-writing phases
- `${CLAUDE_SKILL_DIR}/references/splitting-patterns.md`
- `${CLAUDE_SKILL_DIR}/references/frontmatter-schema.md`
- `${CLAUDE_SKILL_DIR}/references/converter-guide.md`
- `${CLAUDE_SKILL_DIR}/references/quality-checks.md`
- `${CLAUDE_SKILL_DIR}/references/obsidian-bases.md`
- `${CLAUDE_SKILL_DIR}/references/vault-architecture.md`
