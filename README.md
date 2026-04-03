# kb-creator

CLI-first knowledge-base builder and maintainer for Obsidian-first markdown repositories.

`kb-creator` now has two layers:

- `kb`: the primary top-level CLI for initializing, ingesting, compiling, checking, querying, and indexing a KB repo
- `bin/kb-*.py`: low-level JSON-only stage commands preserved for compatibility and agent orchestration

The design target is an agent-callable knowledge compiler, not just a one-shot document conversion pipeline.

## What It Does

- Initializes a KB repository with `raw/`, `wiki/`, `outputs/`, `.kb-artifacts/`, and `.kb-state.json`.
- Ingests source documents into normalized markdown under `raw/sources/`.
- Compiles raw sources into `wiki/summaries/`, `wiki/concepts/`, and `wiki/indexes/`.
- Enriches wiki navigation and cross-links using the existing linking engine.
- Extracts or injects note summaries for downstream model workflows.
- Runs KB health checks and writes both JSON artifacts and markdown reports.
- Materializes query outputs into `outputs/qa/` for reusable research artifacts.
- Builds an expanded machine-readable registry covering notes, sources, and outputs.

## Project Shape

- `bin/`: thin CLI wrappers, including the top-level `kb.py`
- `src/kb_creator/`: core implementation for ingest, compile, operate, and low-level stages
- `references/`: splitting, frontmatter, conversion, and Obsidian guidance
- `templates/`: vault output templates
- `tests/`: regression coverage for core contracts and stages
- `SKILL.md`: thin orchestration wrapper used by higher-level agents

## Operating Contract

Every CLI tool writes exactly one JSON object to stdout. Diagnostics go to stderr. Recoverable situations should stay machine-readable through the `ok`, `warnings`, `errors`, `outputs`, and `artifacts` fields instead of free-form terminal text.

That contract is defined in [src/kb_creator/contracts.py](/Users/ancienttwo/Projects/kb-creator/src/kb_creator/contracts.py).

## Supported Inputs

- `.pdf`
- `.docx`
- `.pptx`
- `.xlsx`
- `.csv`
- `.html` / `.htm`
- `.txt`
- `.md`

## Requirements

- Python 3.11+
- `markitdown`
- `pdfplumber`
- Optional OCR provider env vars for scanned PDFs:
  - `KB_OCR_ENDPOINT`
  - `KB_OCR_API_KEY`

## Install

Using the existing virtualenv:

```bash
.venv/bin/pip install -e ".[dev]"
```

Or with `uv`:

```bash
uv sync --dev
```

The package also exposes a console entrypoint:

```bash
.venv/bin/kb --help
```

## Top-Level CLI

### `kb init`

Initialize a KB repository root.

```bash
.venv/bin/python bin/kb.py init ./my-kb
```

### `kb ingest`

Scan and normalize source documents into `raw/sources/`.

```bash
.venv/bin/python bin/kb.py ingest ./my-kb ./source-docs --enhance-tables
```

### `kb compile`

Incrementally compile `raw/` into `wiki/`.

```bash
.venv/bin/python bin/kb.py compile ./my-kb
```

### `kb health`

Run integrity checks and emit a markdown report under `outputs/health/`.

```bash
.venv/bin/python bin/kb.py health ./my-kb
```

### `kb query`

Materialize a query artifact under `outputs/qa/`.

```bash
.venv/bin/python bin/kb.py query ./my-kb --question "How does the pipeline work?" --update-registry
```

### `kb status`

Show counts, tracked state, and recent outputs.

```bash
.venv/bin/python bin/kb.py status ./my-kb
```

## Low-Level Compatibility Commands

The following commands remain supported and keep their JSON-only stdout contracts:

- `bin/kb-scan.py`
- `bin/kb-convert.py`
- `bin/kb-split.py`
- `bin/kb-link.py`
- `bin/kb-summary.py`
- `bin/kb-registry.py`

These are still the right interface for fine-grained agent orchestration.

### `kb-registry`

Build `vault_registry.json` from the vault.

```bash
.venv/bin/python bin/kb-registry.py ./output/vault --artifacts-dir ./output/.kb-artifacts
```

## Recommended Pipeline

1. Run `kb init`.
2. Run `kb ingest`.
3. Run `kb compile`.
4. Run `kb link`.
5. Run `kb health`.
6. Run `kb query` for reusable answer artifacts.
7. Run `kb registry` or `kb status` as needed.

## Artifacts And Recovery

Run artifacts belong in the KB root:

- `raw/sources/` normalized markdown inputs
- `wiki/summaries/`, `wiki/concepts/`, `wiki/indexes/`
- `outputs/qa/`, `outputs/health/`
- `.kb-artifacts/scan_report.json`
- `.kb-artifacts/health_report.json`
- `.kb-artifacts/vault_registry.json`
- `.kb-artifacts/all_summaries.json`
- `.kb-state.json`

The intent is resumable, agent-friendly execution without parsing terminal prose, while still preserving the older stage commands.

## Development

Run the default verification gate before landing changes:

```bash
.venv/bin/pytest
bash scripts/check-task-sync.sh
bash scripts/check-task-workflow.sh --strict
```

Repo-local agent workflow expectations live in [AGENTS.md](/Users/ancienttwo/Projects/kb-creator/AGENTS.md), while the product contract is tracked in [docs/spec.md](/Users/ancienttwo/Projects/kb-creator/docs/spec.md).
