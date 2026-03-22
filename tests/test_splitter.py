"""Test document splitting engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kb_creator.splitter import detect_boundaries, split_file


CHINESE_LEGAL = """---
source_file: test.pdf
---

# 第一部 总则

## 第1条 释义
定义内容。

## 第2条 范围
范围内容。

# 第二部 发牌制度

## 第3条 要求
要求内容。
更多内容。
更多行。

# 第三部 监管

## 第5条 调查
调查内容。

# 附表一

附表内容。
"""

CHINESE_PATTERNS = [
    {"regex": r"^#\s+第.+部", "priority": 1, "type": "part"},
    {"regex": r"^#\s+附表", "priority": 1, "type": "appendix"},
]


def test_detect_chinese_boundaries():
    boundaries = detect_boundaries(CHINESE_LEGAL, CHINESE_PATTERNS)
    assert len(boundaries) == 4
    types = [b["type"] for b in boundaries]
    assert types == ["part", "part", "part", "appendix"]


def test_detect_english_boundaries():
    content = """# Chapter 1: Introduction

Some text.

# Chapter 2: Methods

More text.

# Appendix A

Extra."""
    patterns = [
        {"regex": r"^#\s+Chapter\s+\d+", "priority": 1, "type": "chapter"},
        {"regex": r"^#\s+Appendix", "priority": 1, "type": "appendix"},
    ]
    boundaries = detect_boundaries(content, patterns)
    assert len(boundaries) == 3


def test_split_file_creates_sections(tmp_path):
    source = tmp_path / "input.md"
    source.write_text(CHINESE_LEGAL, encoding="utf-8")
    out_dir = tmp_path / "output"
    out_dir.mkdir()

    config = {"patterns": CHINESE_PATTERNS, "min_lines": 2, "max_lines": 5000}
    result = split_file(source, out_dir, config)

    assert result.ok
    file_map = result.outputs["file_map"]
    assert len(file_map) >= 4  # preamble + 3 parts + 1 appendix

    # Verify files exist (file_map values are path strings)
    for key, filepath in file_map.items():
        out_file = Path(filepath)
        assert out_file.exists(), f"Missing: {out_file}"
        content = out_file.read_text(encoding="utf-8")
        assert "---" in content  # has frontmatter


def test_split_min_lines_absorption(tmp_path):
    """Sections smaller than min_lines should be absorbed."""
    content = """# 第一部 总则

大量内容。
内容继续。
更多内容。

# 第二部 短部分

短。

# 第三部 正常部分

正常内容。
更多内容。
继续写。
"""
    source = tmp_path / "test.md"
    source.write_text(content, encoding="utf-8")
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    config = {"patterns": CHINESE_PATTERNS, "min_lines": 5, "max_lines": 5000}
    result = split_file(source, out_dir, config)
    assert result.ok
    # Short section should be absorbed
    section_count = len(result.outputs["file_map"])
    assert section_count < 4  # Less than if we split at every boundary
