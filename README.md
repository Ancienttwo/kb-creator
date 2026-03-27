# kb-creator

Agent-first knowledge base creation toolkit for turning source document collections into an Obsidian-ready vault through small JSON-only CLI stages.

## What It Does

- Scans a source directory and reports supported files, language bias, grouping hints, and large-file risks.
- Converts documents to Markdown with `markitdown`, with optional PDF table enhancement via `pdfplumber`.
- Splits large Markdown files into chapter-level notes with frontmatter and stable filenames.
- Injects structural and semantic wiki links across a vault and generates simple category MOCs.
- Extracts summary candidates and injects externally generated TLDRs back into notes.
- Builds a machine-readable vault registry for downstream retrieval and navigation.
- Preserves resumable run artifacts in `.kb-artifacts/` and state in `.kb-state.json`.

## Project Shape

- `bin/`: thin CLI wrappers, one command per pipeline stage
- `src/kb_creator/`: pipeline implementation
- `references/`: splitting, frontmatter, conversion, and Obsidian guidance
- `templates/`: vault output templates
- `tests/`: regression coverage for core contracts and stages
- `SKILL.md`: orchestration contract used by higher-level agents

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

## CLI Surface

### `kb-scan`

Scan a source directory and optionally persist `scan_report.json`.

```bash
.venv/bin/python bin/kb-scan.py ./source-docs --artifacts-dir ./output/.kb-artifacts
```

### `kb-convert`

Check dependencies, convert a single file, or convert a JSON batch manifest.

```bash
.venv/bin/python bin/kb-convert.py --check-deps
.venv/bin/python bin/kb-convert.py ./source/file.pdf ./output/converted --enhance-tables --artifacts-dir ./output/.kb-artifacts
```

### `kb-split`

Split a Markdown file or batch manifest with a JSON config.

```bash
.venv/bin/python bin/kb-split.py ./output/converted/file.md ./output/vault --config ./split-config.json --artifacts-dir ./output/.kb-artifacts
```

Example split config:

```json
{
  "min_lines": 20,
  "max_lines": 5000,
  "patterns": [
    { "regex": "^#{1,2}\\s+Chapter\\s+\\d+", "priority": 1, "type": "chapter" },
    { "regex": "^##\\s+", "priority": 4, "type": "heading2" }
  ]
}
```

### `kb-link`

Preview or apply wiki-link injection.

```bash
.venv/bin/python bin/kb-link.py ./output/vault --mode both --dry-run --artifacts-dir ./output/.kb-artifacts
.venv/bin/python bin/kb-link.py ./output/vault --mode both --artifacts-dir ./output/.kb-artifacts
```

### `kb-summary`

Extract candidates for model-generated summaries, then inject finished summaries.

```bash
.venv/bin/python bin/kb-summary.py ./output/vault --extract --artifacts-dir ./output/.kb-artifacts
.venv/bin/python bin/kb-summary.py ./output/vault --inject ./output/.kb-artifacts/all_summaries.json --format callout
```

### `kb-registry`

Build `vault_registry.json` from the vault.

```bash
.venv/bin/python bin/kb-registry.py ./output/vault --artifacts-dir ./output/.kb-artifacts
```

## Recommended Pipeline

1. Run `kb-convert.py --check-deps`.
2. Scan the source directory with `kb-scan.py`.
3. Convert inputs into Markdown with `kb-convert.py`.
4. Split oversized Markdown files with `kb-split.py`.
5. Run `kb-link.py --dry-run`, inspect the plan, then apply linking.
6. Extract summaries with `kb-summary.py --extract`, generate TLDRs outside the CLI, then inject them.
7. Build the final registry with `kb-registry.py`.

## Artifacts And Recovery

The repo keeps pipeline logic in-repo, but run artifacts belong in the chosen output directory:

- `.kb-artifacts/scan_report.json`
- `.kb-artifacts/convert_report.json` or `.kb-artifacts/convert_single_detail.json`
- `.kb-artifacts/link_report.json`
- `.kb-artifacts/all_summaries.json`
- `.kb-artifacts/vault_registry.json`
- `.kb-state.json`

The intent is resumable, agent-friendly execution without parsing terminal prose.

## Development

Run the default verification gate before landing changes:

```bash
.venv/bin/pytest
bash scripts/check-task-sync.sh
bash scripts/check-task-workflow.sh --strict
```

Repo-local agent workflow expectations live in [AGENTS.md](/Users/ancienttwo/Projects/kb-creator/AGENTS.md), while the product contract is tracked in [docs/spec.md](/Users/ancienttwo/Projects/kb-creator/docs/spec.md).
