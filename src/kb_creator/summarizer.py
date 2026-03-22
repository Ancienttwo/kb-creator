"""Summary extraction and injection for vault notes.

This module does NOT call any LLM. It:
- Extracts candidate content for summarization (--extract)
- Injects externally-generated summaries back into notes (--inject)

The Skill layer is responsible for generating actual TLDR text using model capabilities.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result, log


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Extract frontmatter and body from markdown. Returns (frontmatter_dict, body)."""
    if not content.startswith("---"):
        return {}, content
    end = content.find("---", 3)
    if end == -1:
        return {}, content
    fm_text = content[3:end].strip()
    body = content[end + 3:].strip()
    result: dict[str, Any] = {}
    for line in fm_text.split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip("\"'")
    return result, body


def _extract_candidate(content: str, max_chars: int = 2000) -> str:
    """Extract the first meaningful paragraph(s) as summary candidate."""
    _, body = _parse_frontmatter(content)

    # Skip existing callouts at the top
    lines = body.split("\n")
    start = 0
    for i, line in enumerate(lines):
        if line.startswith("> [!"):
            # Skip this callout block
            start = i + 1
            while start < len(lines) and lines[start].startswith(">"):
                start += 1
            continue
        if line.strip():
            start = i
            break

    # Collect text paragraphs (skip headings, code blocks, tables)
    candidate_lines: list[str] = []
    in_code = False
    char_count = 0

    for line in lines[start:]:
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if line.startswith("#"):
            continue
        if line.startswith("|"):
            continue
        stripped = line.strip()
        if stripped:
            candidate_lines.append(stripped)
            char_count += len(stripped)
            if char_count >= max_chars:
                break

    return "\n".join(candidate_lines)


def extract(vault_dir: Path, artifacts_dir: Path | None = None) -> Result:
    """Extract summary candidates from all notes.

    Returns a JSON structure with candidates that the Skill/Agent can use
    to generate actual summaries via model capabilities.
    """
    result = Result(ok=True, action="summary_extract", inputs={"vault_dir": str(vault_dir)})

    if not vault_dir.is_dir():
        return Result(ok=False, action="summary_extract", errors=[f"Not a directory: {vault_dir}"])

    summaries: dict[str, dict[str, Any]] = {}
    skipped = 0

    for md_file in sorted(vault_dir.rglob("*.md")):
        rel_path = str(md_file.relative_to(vault_dir))
        try:
            content = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            skipped += 1
            continue

        fm, body = _parse_frontmatter(content)

        # Skip index/MOC notes
        if fm.get("type") == "index":
            continue

        # Check if already has a TLDR callout
        has_tldr = "> [!tldr]" in content.lower()

        candidate = _extract_candidate(content)
        if not candidate:
            skipped += 1
            continue

        summaries[rel_path] = {
            "title": md_file.stem,
            "candidate": candidate,
            "has_existing_tldr": has_tldr,
            "category": fm.get("category", ""),
            "parent": fm.get("parent", ""),
        }

    log(f"Extracted {len(summaries)} candidates, skipped {skipped}")

    result.outputs = {
        "total_candidates": len(summaries),
        "skipped": skipped,
    }

    all_summaries = summaries
    if artifacts_dir:
        result.save_artifact("all_summaries", all_summaries, artifacts_dir)
    else:
        # Default: save next to vault
        default_artifacts = vault_dir / ".kb-artifacts"
        result.save_artifact("all_summaries", all_summaries, default_artifacts)

    return result


def inject(vault_dir: Path, summaries_path: Path, fmt: str = "callout") -> Result:
    """Inject summaries from external JSON into vault notes.

    Args:
        vault_dir: Path to vault root
        summaries_path: Path to JSON file with {rel_path: {summary: "...", ...}}
        fmt: "callout" for > [!tldr] blocks, "frontmatter" for summary field in YAML
    """
    result = Result(
        ok=True,
        action="summary_inject",
        inputs={"vault_dir": str(vault_dir), "summaries": str(summaries_path), "format": fmt},
    )

    if not summaries_path.exists():
        return Result(ok=False, action="summary_inject", errors=[f"Summaries file not found: {summaries_path}"])

    data = json.loads(summaries_path.read_text(encoding="utf-8"))
    injected = 0
    skipped = 0

    for rel_path, info in data.items():
        summary_text = info.get("summary", "")
        if not summary_text:
            skipped += 1
            continue

        md_path = vault_dir / rel_path
        if not md_path.exists():
            result.warnings.append(f"Note not found: {rel_path}")
            skipped += 1
            continue

        content = md_path.read_text(encoding="utf-8", errors="replace")

        if fmt == "callout":
            # Remove existing TLDR callout if present
            content = re.sub(
                r"> \[!tldr\].*?\n(?:>.*\n)*",
                "",
                content,
                flags=re.IGNORECASE,
            )

            # Insert after frontmatter
            callout = f"> [!tldr]\n> {summary_text}\n\n"
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    insert_pos = end + 3
                    # Skip trailing newlines after frontmatter
                    while insert_pos < len(content) and content[insert_pos] == "\n":
                        insert_pos += 1
                    content = content[:insert_pos] + "\n" + callout + content[insert_pos:]
                else:
                    content = callout + content
            else:
                content = callout + content

        elif fmt == "frontmatter":
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    fm_section = content[3:end]
                    # Remove existing summary line
                    fm_section = re.sub(r"summary:.*\n", "", fm_section)
                    fm_section = fm_section.rstrip() + f"\nsummary: \"{summary_text}\"\n"
                    content = "---" + fm_section + content[end:]
                else:
                    # Malformed frontmatter (no closing ---)
                    skipped += 1
                    result.warnings.append(f"Malformed frontmatter, skipped: {rel_path}")
                    continue
            else:
                # No frontmatter at all — cannot inject into frontmatter
                skipped += 1
                continue

        md_path.write_text(content, encoding="utf-8")
        injected += 1

    result.outputs = {"injected": injected, "skipped": skipped}
    log(f"Injected {injected} summaries, skipped {skipped}")
    return result
