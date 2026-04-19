# kb-creator

Skill-first knowledge-base builder and maintainer for Obsidian-first markdown repositories.

`kb-creator` is designed to be installed and invoked as an agent Skill. The bundled `kb` CLI remains in the repo as a deterministic runtime and debugging surface, but it is not the intended primary user interface.

The product now models the real two-tier vault shape used in `ziwei`:

- book tier: extract one book, archive its chapters, and build one book-local KB
- root tier: promote distilled notes from a book-local KB into shared root topic directories

## Primary User Experience

Users should:

1. Install the `kb-creator` Skill.
2. Ensure the companion `obsidian-markdown` Skill is also installed.
3. Ask the agent in natural language to create, maintain, lint, or query a KB.

Users should not need to learn `kb init`, `kb compile`, or other CLI subcommands to get value.

## Companion Skill Dependency

`kb-creator` explicitly depends on the external `obsidian-markdown` Skill for any phase that creates or rewrites wiki pages.

Dependency split:

- `kb-creator` owns KB lifecycle, ingestion, provenance, state, worksets, linting, query artifacts, and file placement.
- `obsidian-markdown` owns Obsidian syntax correctness for frontmatter, wikilinks, callouts, embeds, and note-writing conventions.

If the companion Skill is unavailable:

- ingest/scan-only flows may still run when they only populate `raw/`
- wiki-writing phases should stop with a clear dependency error rather than drifting into free-form markdown output

## What It Does

- Initializes a KB repository with `raw/`, `wiki/`, `outputs/`, `.kb-artifacts/`, and `.kb-state.json`.
- Creates first-class KB maintenance artifacts including `KB_SCHEMA.md`, `wiki/index.md`, and `wiki/log.md`.
- Extracts one source book into normalized markdown under `raw/sources/` and archives split chapters under `raw/chapters/<book>/`.
- Builds one book-local KB directory (for example `<Book>知识库/`) with deterministic summaries, concepts, indexes, and worksets.
- Emits root-promotion worksets from book-local KBs and applies them to shared root topic notes through a single-writer step.
- Runs KB health checks and KB lint checks with machine-readable artifacts.
- Materializes query outputs into `outputs/qa/`, with optional versioned query-note file-back into `wiki/queries/`.
- Builds an expanded machine-readable registry covering notes, sources, query outputs, and log history.

## Product Shape

- `SKILL.md`: the primary product contract for agent use
- `src/kb_creator/`: bundled deterministic runtime and KB operations
- `bin/`: CLI wrappers for developer/debug use
- `references/`: implementation notes and Obsidian guidance
- `tests/`: regression coverage for runtime contracts

## Installation

### Recommended: Skill Installation

Install:

- `kb-creator`
- `obsidian-markdown`

Then invoke the Skill in natural language through the host agent.

### Developer / Debug Installation

For local development and contract verification:

```bash
.venv/bin/pip install -e ".[dev]"
```

Or:

```bash
uv sync --dev
```

This exposes the internal `kb` CLI runtime for debugging:

```bash
.venv/bin/kb --help
```

## Dependency Verification

Before any wiki-writing workflow, the agent/operator should verify:

- the `kb-creator` Skill runtime is installed and healthy
- the external `obsidian-markdown` Skill is available

If `obsidian-markdown` is missing, do not proceed with compile phases that create wiki notes, query file-back, or lint-guided wiki repairs.

## Managed Artifacts

Run artifacts belong in the KB root:

- `raw/sources/`
- `raw/chapters/<book>/`
- `.kb-artifacts/permits/`
- `.kb-artifacts/root-promotion/`
- `KB_SCHEMA.md`
- `wiki/summaries/`, `wiki/concepts/`, `wiki/indexes/`, `wiki/queries/<slug>.md`, `wiki/queries/<slug>--vN.md`, `wiki/index.md`, `wiki/log.md`
- `outputs/qa/`, `outputs/health/`
- `.kb-artifacts/scan_report.json`
- `.kb-artifacts/health_report.json`
- `.kb-artifacts/lint_report.json`
- `.kb-artifacts/vault_registry.json`
- `.kb-artifacts/all_summaries.json`
- `.kb-artifacts/compile_workset.json`
- `.kb-state.json`

## Canonical Runtime Flow

The intended runtime sequence is now:

```text
book source
  -> kb build-book
    -> raw full text
    -> chapter archive
    -> book-local KB
    -> review-needed or ready
      -> kb distill-to-root
        -> promotion workset
          -> kb apply-root-promotion
            -> shared root topic notes
```

`kb init`, `kb ingest`, `kb compile`, and the `bin/kb-*.py` wrappers still exist as low-level/runtime surfaces. They are no longer the primary product story.

## Write-Permit Artifacts

Write-capable steps use signed permit artifacts instead of a plain `--yes` style flag.

- `kb build-book` requires a `build-book` permit targeted at the book slug.
- `kb apply-root-promotion` requires an `apply-root-promotion` permit targeted at the same book slug.
- The debug helper `kb issue-permit` exists for tests and operator workflows. The signer key comes from `KB_WRITE_PERMIT_KEY`.

If the permit is missing, expired, or signed for the wrong scope/target, the write step fails closed.

## Developer Notes

The internal CLI still preserves JSON-only stdout contracts. Diagnostics go to stderr. This is the stable runtime layer that powers the Skill and should remain safe for tests, automation, and fallback debugging.

Run the default verification gate before landing changes:

```bash
.venv/bin/pytest
python3 -m py_compile src/kb_creator/*.py bin/kb.py bin/kb-*.py
bash scripts/check-task-sync.sh
bash scripts/check-task-workflow.sh --strict
```

Repo-local agent workflow expectations live in [AGENTS.md](/Users/ancienttwo/Projects/kb-creator/AGENTS.md), while the product contract is tracked in [docs/spec.md](/Users/ancienttwo/Projects/kb-creator/docs/spec.md).
