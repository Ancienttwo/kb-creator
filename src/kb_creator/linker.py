"""Wiki-link injection engine for Obsidian vaults.

Generates structural links (parent-child, sibling) and semantic links
(cross-references detected in text). Supports dry-run mode.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result, log

# Cross-reference patterns for Chinese/English documents
XREF_PATTERNS = [
    # Chinese: 見第X章, 參照《XX》, 根據第X條
    re.compile(r"[見见参參](?:照|閱|阅)?[《「](.+?)[》」]"),
    re.compile(r"(?:根[據据]|依照|按照)第[\s]*(\S+?)[條条部章節节]"),
    re.compile(r"[見见]第[\s]*(\S+?)[條条部章節节]"),
    # English: see Chapter N, refer to Section N, as per Part N
    re.compile(r"(?:see|refer to|as per)\s+(Chapter|Section|Part)\s+(\S+)", re.IGNORECASE),
]


def _parse_frontmatter(content: str) -> dict[str, Any]:
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}
    end = content.find("---", 3)
    if end == -1:
        return {}
    fm_text = content[3:end].strip()
    result: dict[str, Any] = {}
    for line in fm_text.split("\n"):
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip().strip("\"'")
            if value.startswith("[") and value.endswith("]"):
                value = [v.strip().strip("\"'") for v in value[1:-1].split(",") if v.strip()]
            result[key] = value
    return result


def _scan_vault(vault_dir: Path) -> dict[str, dict[str, Any]]:
    """Build index of all notes in the vault. Returns {stem: {path, frontmatter, title}}."""
    index: dict[str, dict[str, Any]] = {}
    for md_file in vault_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8", errors="replace")
        fm = _parse_frontmatter(content)
        stem = md_file.stem
        index[stem] = {
            "path": str(md_file.relative_to(vault_dir)),
            "frontmatter": fm,
            "title": stem,
            "parent": fm.get("parent", ""),
            "source_file": fm.get("source_file", ""),
            "category": fm.get("category", ""),
        }
    return index


def _find_structural_links(index: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Find parent-child and sibling relationships based on source_file and parent fields."""
    links: list[dict[str, str]] = []
    # Group notes by source_file
    by_source: dict[str, list[str]] = {}
    for stem, info in index.items():
        src = info.get("source_file", "")
        if src:
            by_source.setdefault(src, []).append(stem)

    for src, siblings in by_source.items():
        if len(siblings) <= 1:
            continue
        # Link siblings to each other (prev/next)
        sorted_siblings = sorted(siblings)
        for i, stem in enumerate(sorted_siblings):
            if i > 0:
                links.append({"from": stem, "to": sorted_siblings[i - 1], "type": "prev_sibling"})
            if i < len(sorted_siblings) - 1:
                links.append({"from": stem, "to": sorted_siblings[i + 1], "type": "next_sibling"})

    # Parent links
    for stem, info in index.items():
        parent = info.get("parent", "")
        if parent and parent in index:
            links.append({"from": stem, "to": parent, "type": "parent"})

    return links


def _find_semantic_links(vault_dir: Path, index: dict[str, dict[str, Any]]) -> list[dict[str, str]]:
    """Detect cross-references in note content by matching against note titles."""
    links: list[dict[str, str]] = []
    title_set = set(index.keys())

    for stem, info in index.items():
        md_path = vault_dir / info["path"]
        try:
            content = md_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Check if any other note title appears in this note's content
        for other_stem in title_set:
            if other_stem == stem:
                continue
            if len(other_stem) < 3:
                continue
            if other_stem in content:
                # Verify it's not already a wikilink
                wikilink = f"[[{other_stem}]]"
                if wikilink not in content:
                    links.append({"from": stem, "to": other_stem, "type": "semantic"})

        # Check cross-reference patterns
        for pattern in XREF_PATTERNS:
            for match in pattern.finditer(content):
                ref_text = match.group(1) if match.lastindex else match.group(0)
                # Try to match ref_text to a note title
                for other_stem in title_set:
                    if other_stem == stem:
                        continue
                    if ref_text in other_stem or other_stem in ref_text:
                        links.append({"from": stem, "to": other_stem, "type": "xref"})
                        break

    return links


def _generate_moc(
    vault_dir: Path,
    index: dict[str, dict[str, Any]],
    category: str,
    notes: list[str],
) -> str:
    """Generate a Map of Content markdown string for a category."""
    lines = [
        "---",
        f"category: {category}",
        "type: index",
        "---",
        "",
        f"# {category}",
        "",
    ]
    for stem in sorted(notes):
        info = index.get(stem, {})
        lines.append(f"- [[{stem}]]")
    lines.append("")
    return "\n".join(lines)


def link(
    vault_dir: Path,
    mode: str = "both",
    dry_run: bool = False,
    artifacts_dir: Path | None = None,
) -> Result:
    """Scan vault and generate/inject wiki links.

    Args:
        vault_dir: Path to the Obsidian vault root
        mode: "structural", "semantic", or "both"
        dry_run: If True, return patch plan without modifying files
        artifacts_dir: Where to save link_report.json
    """
    result = Result(ok=True, action="link", inputs={"vault_dir": str(vault_dir), "mode": mode, "dry_run": dry_run})

    if not vault_dir.is_dir():
        return Result(ok=False, action="link", errors=[f"Vault directory not found: {vault_dir}"])

    log(f"Scanning vault: {vault_dir}")
    index = _scan_vault(vault_dir)
    log(f"Found {len(index)} notes")

    structural_links: list[dict[str, str]] = []
    semantic_links: list[dict[str, str]] = []

    if mode in ("structural", "both"):
        structural_links = _find_structural_links(index)
        log(f"Found {len(structural_links)} structural links")

    if mode in ("semantic", "both"):
        semantic_links = _find_semantic_links(vault_dir, index)
        log(f"Found {len(semantic_links)} semantic links")

    # Deduplicate semantic links
    seen = set()
    deduped_semantic: list[dict[str, str]] = []
    for link_item in semantic_links:
        key = (link_item["from"], link_item["to"])
        if key not in seen:
            seen.add(key)
            deduped_semantic.append(link_item)
    semantic_links = deduped_semantic

    # Generate MOCs by category
    by_category: dict[str, list[str]] = {}
    for stem, info in index.items():
        cat = info.get("category", "uncategorized")
        if cat:
            by_category.setdefault(cat, []).append(stem)

    moc_files: list[str] = []

    if not dry_run:
        # Inject wikilinks into notes
        for link_item in structural_links + semantic_links:
            from_stem = link_item["from"]
            to_stem = link_item["to"]
            if from_stem not in index:
                continue
            md_path = vault_dir / index[from_stem]["path"]
            try:
                content = md_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            wikilink = f"[[{to_stem}]]"
            if wikilink in content:
                continue

            # For structural links, add to frontmatter area or bottom
            if link_item["type"] in ("parent", "prev_sibling", "next_sibling"):
                # Add navigation section at bottom if not exists
                nav_marker = "## 导航"
                if nav_marker not in content:
                    content += f"\n\n{nav_marker}\n"
                if link_item["type"] == "parent":
                    content += f"- 上级: {wikilink}\n"
                elif link_item["type"] == "prev_sibling":
                    content += f"- 上一节: {wikilink}\n"
                elif link_item["type"] == "next_sibling":
                    content += f"- 下一节: {wikilink}\n"
            # Semantic links: add to related section
            elif link_item["type"] in ("semantic", "xref"):
                related_marker = "## 相关"
                if related_marker not in content:
                    content += f"\n\n{related_marker}\n"
                content += f"- {wikilink}\n"

            md_path.write_text(content, encoding="utf-8")

        # Write MOC files
        for cat, notes in by_category.items():
            if len(notes) < 2:
                continue
            moc_content = _generate_moc(vault_dir, index, cat, notes)
            # Find category directory
            first_note = index[notes[0]]
            cat_dir = (vault_dir / first_note["path"]).parent
            moc_path = cat_dir / f"_{cat} MOC.md"
            moc_path.write_text(moc_content, encoding="utf-8")
            moc_files.append(str(moc_path.relative_to(vault_dir)))

    result.outputs = {
        "total_notes": len(index),
        "structural_links": len(structural_links),
        "semantic_links": len(semantic_links),
        "moc_files": moc_files,
        "structural_detail": structural_links[:50],  # Cap for JSON size
        "semantic_detail": semantic_links[:50],
    }

    if dry_run:
        result.outputs["patch_plan"] = {
            "structural": structural_links,
            "semantic": semantic_links,
            "mocs": list(by_category.keys()),
        }

    if artifacts_dir:
        report = {
            "total_notes": len(index),
            "structural_links": structural_links,
            "semantic_links": semantic_links,
            "moc_files": moc_files,
        }
        result.save_artifact("link_report", report, artifacts_dir)

    return result
