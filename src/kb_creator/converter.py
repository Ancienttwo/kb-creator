"""Document-to-Markdown conversion orchestrator.

Wraps markitdown (CLI, subprocess) and pdfplumber (Python import) to convert
various document formats into Markdown.  Every public function returns a
contracts.Result so the CLI layer can emit a single JSON object.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any

from kb_creator.contracts import Result, log

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_EXTENSIONS: set[str] = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".csv", ".html", ".htm", ".txt", ".md",
}

_CJK_GARBLE_RE = re.compile(r"[\ufffd]{3,}")  # 3+ replacement chars in a row

# ---------------------------------------------------------------------------
# Dependency checks
# ---------------------------------------------------------------------------


def _has_markitdown() -> bool:
    """Check if markitdown is importable via the current Python interpreter."""
    import subprocess as _sp
    try:
        proc = _sp.run(
            [sys.executable, "-c", "import markitdown"],
            capture_output=True, timeout=10,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _has_pdfplumber() -> bool:
    try:
        import pdfplumber as _  # noqa: F401
        return True
    except ImportError:
        return False


def _has_ocr_provider() -> bool:
    return bool(os.environ.get("KB_OCR_ENDPOINT") and os.environ.get("KB_OCR_API_KEY"))


def check_deps() -> Result:
    """Report which conversion dependencies are available."""
    markitdown_ok = _has_markitdown()
    pdfplumber_ok = _has_pdfplumber()
    ocr_ok = _has_ocr_provider()

    ready: list[str] = []
    missing: list[str] = []
    available: list[str] = []

    if markitdown_ok:
        ready.append("markitdown")
    else:
        missing.append("markitdown")

    if pdfplumber_ok:
        available.append("pdfplumber")
    else:
        available.append("pdfplumber (not installed)")

    if ocr_ok:
        available.append("ocr_provider")
    else:
        available.append("ocr_provider (env vars not set)")

    return Result(
        ok=len(missing) == 0,
        action="check_deps",
        outputs={
            "ready": ready,
            "missing": missing,
            "available": available,
            "markitdown": markitdown_ok,
            "pdfplumber": pdfplumber_ok,
            "ocr_provider": ocr_ok,
        },
    )


# ---------------------------------------------------------------------------
# Quality check
# ---------------------------------------------------------------------------


def quality_check(md_path: Path, source_path: Path) -> dict[str, Any]:
    """Assess conversion quality of a produced Markdown file.

    Returns ``{ok, issues, line_count, encoding}``.
    """
    issues: list[str] = []
    encoding = "utf-8"
    line_count = 0

    try:
        text = md_path.read_text(encoding="utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        try:
            text = md_path.read_text(encoding="latin-1")
            encoding = "latin-1"
            issues.append("file decoded as latin-1 instead of utf-8")
        except Exception as exc:
            return {"ok": False, "issues": [f"unreadable: {exc}"], "line_count": 0, "encoding": "unknown"}

    lines = text.splitlines()
    line_count = len(lines)

    if line_count == 0:
        issues.append("empty output")

    # CJK garbled character detection
    if _CJK_GARBLE_RE.search(text):
        issues.append("possible garbled CJK characters detected")

    # Very short output for a non-trivial source is suspicious
    source_size = source_path.stat().st_size if source_path.exists() else 0
    if source_size > 10_000 and line_count < 3:
        issues.append(f"suspiciously short output ({line_count} lines) for {source_size}-byte source")

    return {
        "ok": len(issues) == 0,
        "issues": issues,
        "line_count": line_count,
        "encoding": encoding,
    }


# ---------------------------------------------------------------------------
# PDF table enhancement via pdfplumber
# ---------------------------------------------------------------------------


def _enhance_tables_pdf(pdf_path: Path, md_text: str) -> str:
    """Extract tables from a PDF via pdfplumber and append as Markdown."""
    try:
        import pdfplumber
    except ImportError:
        log("pdfplumber not installed; skipping table enhancement")
        return md_text

    tables_md: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                page_tables = page.extract_tables()
                if not page_tables:
                    continue
                for t_idx, table in enumerate(page_tables, 1):
                    if not table or not table[0]:
                        continue
                    header = table[0]
                    rows = table[1:]
                    # Build Markdown table
                    header_cells = [str(c or "") for c in header]
                    md_table_lines = [
                        "| " + " | ".join(header_cells) + " |",
                        "| " + " | ".join("---" for _ in header_cells) + " |",
                    ]
                    for row in rows:
                        cells = [str(c or "") for c in row]
                        # Pad if row is shorter than header
                        while len(cells) < len(header_cells):
                            cells.append("")
                        md_table_lines.append("| " + " | ".join(cells[: len(header_cells)]) + " |")
                    tables_md.append(
                        f"\n\n<!-- pdfplumber table: page {page_num}, table {t_idx} -->\n"
                        + "\n".join(md_table_lines)
                    )
    except Exception as exc:
        log(f"pdfplumber table extraction failed: {exc}")
        return md_text

    if tables_md:
        md_text += "\n\n---\n\n## Extracted Tables (pdfplumber)\n" + "\n".join(tables_md) + "\n"
    return md_text


# ---------------------------------------------------------------------------
# Scanned-PDF detection
# ---------------------------------------------------------------------------


def _is_scanned_pdf(pdf_path: Path) -> bool:
    """Heuristic: a scanned PDF has very little extractable text per page."""
    try:
        import pdfplumber
    except ImportError:
        return False

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                return False
            sample = pdf.pages[: min(3, len(pdf.pages))]
            total_chars = sum(len((p.extract_text() or "").strip()) for p in sample)
            avg = total_chars / len(sample)
            return avg < 30  # fewer than 30 chars/page → likely scanned
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Single-file conversion
# ---------------------------------------------------------------------------


def _run_markitdown(input_path: Path, output_path: Path) -> tuple[bool, str]:
    """Call markitdown via the current Python interpreter and write result to *output_path*.

    Returns ``(success, error_message)``.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "markitdown", str(input_path)],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        return False, "Python interpreter not found"
    except subprocess.TimeoutExpired:
        return False, "markitdown timed out (300s)"

    if proc.returncode != 0:
        stderr_tail = (proc.stderr or "").strip()[-500:]
        return False, f"markitdown exited {proc.returncode}: {stderr_tail}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(proc.stdout, encoding="utf-8")
    return True, ""


def convert_file(
    input_path: Path,
    output_dir: Path,
    enhance_tables: bool = False,
) -> Result:
    """Convert a single document to Markdown.

    Returns a Result with ``outputs.md_path`` on success.
    """
    input_path = Path(input_path).resolve()
    output_dir = Path(output_dir).resolve()

    result = Result(ok=False, action="convert_file", inputs={"input": str(input_path), "output_dir": str(output_dir)})

    # --- validation ---
    if not input_path.exists():
        result.errors.append(f"input not found: {input_path}")
        return result

    ext = input_path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        result.errors.append(f"unsupported format: {ext}")
        return result

    # Passthrough for plain text / Markdown
    if ext in {".txt", ".md"}:
        out_path = output_dir / (input_path.stem + ".md")
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(input_path.read_bytes())
        qc = quality_check(out_path, input_path)
        result.ok = True
        result.outputs = {"md_path": str(out_path), "quality": qc}
        if not qc["ok"]:
            result.warnings.extend(qc["issues"])
        return result

    # Scanned-PDF detection
    if ext == ".pdf" and _is_scanned_pdf(input_path):
        if not _has_ocr_provider():
            result.ok = True
            result.outputs = {
                "status": "needs_provider",
                "reason": "scanned PDF detected but OCR provider env vars (KB_OCR_ENDPOINT, KB_OCR_API_KEY) not set",
            }
            result.warnings.append("scanned PDF requires OCR provider")
            return result

    # --- markitdown ---
    if not _has_markitdown():
        result.errors.append("markitdown is not installed; cannot convert")
        return result

    out_path = output_dir / (input_path.stem + ".md")
    success, err = _run_markitdown(input_path, out_path)
    if not success:
        result.errors.append(err)
        return result

    log(f"converted {input_path.name} -> {out_path.name}")

    # --- optional table enhancement ---
    if enhance_tables and ext == ".pdf":
        if _has_pdfplumber():
            md_text = out_path.read_text(encoding="utf-8")
            enhanced = _enhance_tables_pdf(input_path, md_text)
            if enhanced != md_text:
                out_path.write_text(enhanced, encoding="utf-8")
                log(f"enhanced tables in {out_path.name}")
        else:
            result.warnings.append("pdfplumber not installed; table enhancement skipped")

    # --- quality check ---
    qc = quality_check(out_path, input_path)
    result.ok = True
    result.outputs = {"md_path": str(out_path), "quality": qc}
    if not qc["ok"]:
        result.warnings.extend(qc["issues"])

    return result


# ---------------------------------------------------------------------------
# Batch conversion
# ---------------------------------------------------------------------------


def convert_batch(
    file_list: list[Path] | Path,
    output_dir: Path,
    enhance_tables: bool = False,
    artifacts_dir: Path | None = None,
) -> Result:
    """Convert a list of files (or a JSON file containing such a list).

    Returns a summary Result with per-file status in ``outputs.files``.
    """
    # Resolve file list
    if isinstance(file_list, Path):
        file_list = Path(file_list).resolve()
        if not file_list.exists():
            return Result(
                ok=False,
                action="convert_batch",
                inputs={"file_list": str(file_list)},
                errors=[f"file list not found: {file_list}"],
            )
        try:
            raw = json.loads(file_list.read_text(encoding="utf-8"))
            paths = [Path(p) for p in raw]
        except (json.JSONDecodeError, TypeError) as exc:
            return Result(
                ok=False,
                action="convert_batch",
                inputs={"file_list": str(file_list)},
                errors=[f"invalid file list JSON: {exc}"],
            )
    else:
        paths = [Path(p) for p in file_list]

    output_dir = Path(output_dir).resolve()

    result = Result(
        ok=True,
        action="convert_batch",
        inputs={"file_count": len(paths), "output_dir": str(output_dir)},
    )

    per_file: list[dict[str, Any]] = []
    converted = 0
    skipped = 0
    errored = 0

    for p in paths:
        fr = convert_file(p, output_dir, enhance_tables=enhance_tables)
        entry: dict[str, Any] = {"source": str(p), "ok": fr.ok}
        if fr.ok:
            converted += 1
            entry["outputs"] = fr.outputs
        else:
            errored += 1
            entry["errors"] = fr.errors
        if fr.warnings:
            entry["warnings"] = fr.warnings
        per_file.append(entry)

    result.outputs = {
        "converted": converted,
        "skipped": skipped,
        "errored": errored,
        "total": len(paths),
        "files": per_file,
    }

    if errored and converted == 0:
        result.ok = False
    elif errored:
        result.warnings.append(f"{errored}/{len(paths)} files had errors")

    # Persist per-file detail as artifact when requested
    if artifacts_dir:
        result.save_artifact("convert_report", per_file, Path(artifacts_dir))

    return result
