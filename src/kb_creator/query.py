"""Query materialization for KB repositories."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result
from kb_creator.kb import KBLayout, _load_state


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[\w\u3400-\u9fff]+", text.lower()) if len(token) >= 2]


def run_query(kb_root: Path, question: str, limit: int = 5, update_registry: bool = False) -> Result:
    """Resolve relevant wiki notes and materialize a markdown answer artifact."""
    layout = KBLayout(kb_root.resolve())
    state = _load_state(layout)
    result = Result(
        ok=True,
        action="kb_query",
        inputs={"kb_root": str(layout.root), "question": question, "limit": limit},
    )

    note_entries: list[dict[str, Any]] = []
    tokens = set(_tokenize(question))
    for note_path in sorted(layout.wiki_dir.rglob("*.md")):
        content = note_path.read_text(encoding="utf-8", errors="replace")
        haystack = content.lower()
        score = sum(haystack.count(token) for token in tokens)
        if score <= 0:
            continue
        preview = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not stripped.startswith("---"):
                preview.append(stripped)
            if len(" ".join(preview)) > 280:
                break
        note_entries.append({
            "path": note_path.relative_to(layout.root).as_posix(),
            "score": score,
            "preview": " ".join(preview)[:320].strip(),
        })

    note_entries.sort(key=lambda item: (-item["score"], item["path"]))
    selected = note_entries[:limit]

    timestamp = datetime.now(timezone.utc)
    slug = re.sub(r"-{2,}", "-", re.sub(r"[^\w\u3400-\u9fff]+", "-", question.lower())).strip("-") or "query"
    output_path = layout.outputs_qa_dir / f"{timestamp.strftime('%Y%m%d-%H%M%S')}-{slug}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sources_field = ", ".join(f'"{entry["path"]}"' for entry in selected)
    question_yaml = question.replace('"', '\\"')

    lines = [
        "---",
        f'question: "{question_yaml}"',
        f'asked_at: "{timestamp.date().isoformat()}"',
        f"sources: [{sources_field}]",
        'type: "qa-output"',
        "---",
        "",
        f"# {question}",
        "",
        "## Answer Draft",
        "",
    ]
    if selected:
        lines.append("This query matched the following knowledge artifacts. Use them as grounded context for a downstream LLM answer or manual synthesis.")
    else:
        lines.append("No matching wiki notes were found for this query.")
    lines.extend(["", "## Sources", ""])
    for entry in selected:
        lines.append(f"- [[{Path(entry['path']).with_suffix('').as_posix()}]] (score: {entry['score']})")
        if entry["preview"]:
            lines.append(f"  - {entry['preview']}")
    lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")

    if update_registry:
        from kb_creator.registry import build_registry

        build_registry(layout.root, artifacts_dir=layout.artifacts_dir)

    state.last_query_output = str(output_path.relative_to(layout.root))
    state.phase = "query"
    state.save(layout.root)

    result.outputs = {
        "answer_path": str(output_path),
        "source_count": len(selected),
        "sources": selected,
    }
    return result
