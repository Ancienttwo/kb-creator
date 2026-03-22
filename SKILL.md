---
name: kb-creator
description: |
  Agent-first knowledge base creator for Obsidian vaults. Orchestrates the full pipeline:
  scan source documents → convert to markdown → split large files → tag and group →
  inject wiki links → generate summaries → build registry.
  Use when asked to "create knowledge base", "build vault from documents", "convert docs to Obsidian",
  "知识库", "文档转换", "建 vault", or "KB from source files".
  Do not use for: single note editing, small-scale summarization, or vault querying.
---

# kb-creator

Agent-first knowledge base creation skill. Converts source documents into a structured Obsidian vault with chapters, tags, wiki links, summaries, and a searchable registry.

## Architecture

- **Skill (this file)** = orchestration layer. Makes decisions, calls model for summaries, asks user questions.
- **CLI tools (`bin/`)** = execution layer. Non-interactive, JSON-only stdout, logs to stderr.
- **All intermediate artifacts** persist to `<output_dir>/.kb-artifacts/` for recovery and multi-agent collaboration.

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

## Workflow

### Phase 0: Environment & Discovery

1. **Check dependencies**:
   ```bash
   ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-convert.py --check-deps
   ```
   Parse the JSON result. If `missing` array is non-empty, output installation commands and ask the calling agent to execute them.

2. **Check for existing state** (if `resume: true`):
   Read `<output_dir>/.kb-state.json`. If exists, report progress and ask: continue or restart?

3. **Scan source directory**:
   ```bash
   ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-scan.py <source_dir> --artifacts-dir <output_dir>/.kb-artifacts
   ```
   Parse scan_report.json. Present summary to user:
   - Total files by format
   - Language detected
   - Suggested grouping strategy
   - Large files that need splitting

4. **Confirm parameters**: If `grouping_strategy: auto`, use the scan suggestions. If user wants manual grouping, ask for category assignments.

5. **Initialize state**: Write `.kb-state.json` with all parameters.

### Phase 1: Conversion

For each source file (or batch):

```bash
${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-convert.py <input> <output_dir>/converted --enhance-tables --artifacts-dir <output_dir>/.kb-artifacts
```

Parse the convert_report. For each file:
- `status: "converted"` → proceed
- `status: "needs_provider"` → warn user, skip (don't block pipeline)
- `status: "quality_issues"` → report issues, let user decide

Update `.kb-state.json` after each batch.

### Phase 2: Structuring

1. **Identify files needing splitting**: Check convert_report for files exceeding the line threshold (default: 2000 lines).

2. **Detect splitting patterns**: Read the converted markdown files and analyze heading structure. Load `${CLAUDE_SKILL_DIR}/references/splitting-patterns.md` for pattern matching.

3. **Generate split config** per file or use user-provided `split_config`.

4. **Execute splitting**:
   ```bash
   ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-split.py <input.md> <output_dir>/vault --config <split-config.json> --artifacts-dir <output_dir>/.kb-artifacts
   ```

5. **Organize into categories**: Move files into category subdirectories based on grouping strategy.

6. **Inject frontmatter**: Ensure each note has YAML frontmatter per `${CLAUDE_SKILL_DIR}/references/frontmatter-schema.md`.

Update `.kb-state.json`.

### Phase 3: Linking

1. **Dry-run first**:
   ```bash
   ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-link.py <vault_dir> --mode both --dry-run --artifacts-dir <output_dir>/.kb-artifacts
   ```
   Review the patch plan. Check link counts are reasonable.

2. **Execute linking**:
   ```bash
   ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-link.py <vault_dir> --mode both --artifacts-dir <output_dir>/.kb-artifacts
   ```

3. **Verify**: Check link_report for warnings or anomalies.

Update `.kb-state.json`.

### Phase 4: Summaries & Registry

1. **Extract summary candidates**:
   ```bash
   ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-summary.py <vault_dir> --extract --artifacts-dir <output_dir>/.kb-artifacts
   ```

2. **Generate TLDR summaries** (if `summary_mode: generate`):
   - Read `all_summaries.json`
   - For each candidate, use model capabilities to generate a one-line TLDR
   - Write summaries back to `all_summaries.json` with `summary` field populated
   - Process in batches to manage context

3. **Inject summaries**:
   ```bash
   ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-summary.py <vault_dir> --inject <output_dir>/.kb-artifacts/all_summaries.json --format callout
   ```

4. **Build registry**:
   ```bash
   ${CLAUDE_SKILL_DIR}/.venv/bin/python ${CLAUDE_SKILL_DIR}/bin/kb-registry.py <vault_dir> --artifacts-dir <output_dir>/.kb-artifacts
   ```

5. **Generate topic aliases** (Skill responsibility):
   Analyze categories and tags to produce `topic_aliases.yml` with simplified/traditional Chinese and English synonyms. Write to `<vault_dir>/topic_aliases.yml`.

Update `.kb-state.json`.

### Phase 5: Obsidian Views & Completion

1. **Generate Base view** (if vault has Obsidian Bases support):
   Use `${CLAUDE_SKILL_DIR}/templates/base-view.template.yaml` as reference to create a `.base` file in the vault's `Bases/` folder.

2. **Generate progress dashboard**:
   Use `${CLAUDE_SKILL_DIR}/templates/progress.template.md` to create a progress overview note.

3. **Generate homepage MOC**:
   Create a `首页.md` or `index.md` linking all category MOCs.

4. **Final report**:
   Summarize: total files, categories, notes, links, summaries, quality issues.

5. Mark `.kb-state.json` phase as `done`.

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
- `${CLAUDE_SKILL_DIR}/references/vault-architecture.md` — Phase 0, 3, 5
