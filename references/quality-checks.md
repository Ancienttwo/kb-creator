# 转换品质验证规则

文件转换完成后执行以下品质检查。每条规则包含：检查名称、判定条件、严重级别（error/warning）、修复建议。

## 检查项一览

| 检查 | 级别 | 说明 |
|------|------|------|
| 行数检查 | error | 转换结果不能为空 |
| 编码验证 | error | 必须是有效 UTF-8 |
| CJK 乱码检测 | error | 不应包含常见乱码模式 |
| 表格完整性 | warning | Markdown 表格管线符应平衡 |
| 内容完整度 | warning | 转换后文件大小不应过小 |
| 标题结构 | warning | 应包含至少一个结构化标题 |

## 1. 行数检查 (line_count)

转换后的 Markdown 文件至少应有有效内容行。

```python
def check_line_count(content: str) -> dict:
    lines = [l for l in content.splitlines() if l.strip()]
    if len(lines) == 0:
        return {"pass": False, "level": "error", "msg": "转换结果为空（0 行有效内容）"}
    if len(lines) < 3:
        return {"pass": False, "level": "warning", "msg": f"内容过少（仅 {len(lines)} 行），可能转换不完整"}
    return {"pass": True}
```

## 2. 编码验证 (encoding)

确保文件为有效 UTF-8 编码，无非法字节序列。

```python
def check_encoding(file_path: str) -> dict:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            f.read()
        return {"pass": True}
    except UnicodeDecodeError as e:
        return {
            "pass": False,
            "level": "error",
            "msg": f"非有效 UTF-8 编码: {e}",
            "fix": "尝试用 chardet 检测原始编码后重新转换"
        }
```

## 3. CJK 乱码检测 (garbled_cjk)

检测常见的中日韩文字乱码模式。

### 常见乱码特征

| 模式 | 说明 | 示例 |
|------|------|------|
| 连续替换字符 | Unicode replacement character | `\ufffd\ufffd\ufffd` |
| Big5 误读为 UTF-8 | 台湾文件常见 | `é¢¨éªç®¡ç` |
| GBK 误读为 UTF-8 | 简体中文文件 | `ÖÐ¹ú` |
| Latin-1 误读 | 西欧编码干扰 | `æ·±å³` |
| 控制字符密集 | 二进制残留 | `\x00\x01\x02` |

```python
import re

GARBLED_PATTERNS = [
    # 连续 3+ 个 Unicode replacement character
    (r"\ufffd{3,}", "连续替换字符 (U+FFFD)"),
    # Big5 误读模式：连续拉丁扩展字符 + CJK 片段
    (r"[é|è|ê|ë|à|á|â|ã|ä|å|æ|ç|ì|í|î|ï|ò|ó|ô|õ|ö|ù|ú|û|ü]{3,}", "疑似 Big5/GBK 误读"),
    # 密集控制字符（非换行/制表符）
    (r"[\x00-\x08\x0b\x0c\x0e-\x1f]{2,}", "控制字符残留"),
    # 高密度非常用 Unicode 区（Private Use Area）
    (r"[\ue000-\uf8ff]{3,}", "Private Use Area 字符密集"),
]

def check_garbled_cjk(content: str) -> dict:
    issues = []
    for pattern, desc in GARBLED_PATTERNS:
        matches = re.findall(pattern, content)
        if matches:
            issues.append(f"{desc}: 发现 {len(matches)} 处")
    if issues:
        return {
            "pass": False,
            "level": "error",
            "msg": "检测到疑似乱码",
            "details": issues,
            "fix": "检查原始文件编码，尝试 Big5/GBK -> UTF-8 转码后重新处理"
        }
    return {"pass": True}
```

## 4. 表格完整性 (table_integrity)

Markdown 表格的管线符 `|` 应在每行数量一致。

```python
def check_table_integrity(content: str) -> dict:
    lines = content.splitlines()
    issues = []
    table_start = None
    expected_pipes = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            pipe_count = stripped.count("|")
            if table_start is None:
                table_start = i
                expected_pipes = pipe_count
            elif pipe_count != expected_pipes:
                issues.append(
                    f"行 {i+1}: 管线符数量 {pipe_count}，预期 {expected_pipes}（表格起始行 {table_start+1}）"
                )
        else:
            table_start = None
            expected_pipes = None

    if issues:
        return {
            "pass": False,
            "level": "warning",
            "msg": f"发现 {len(issues)} 处表格列数不一致",
            "details": issues[:5],  # 最多显示 5 处
            "fix": "检查原始文件中对应表格是否有合并单元格，手动修正管线符"
        }
    return {"pass": True}
```

## 5. 内容完整度 (content_completeness)

比较原始文件大小与转换后文件大小的比率。

```python
def check_content_completeness(source_size_kb: int, converted_content: str) -> dict:
    converted_size_kb = len(converted_content.encode("utf-8")) / 1024
    if source_size_kb == 0:
        return {"pass": True}

    ratio = converted_size_kb / source_size_kb

    # PDF/DOCX 转 Markdown 通常文本量会减少（去掉格式信息）
    # 但不应减少太多
    if ratio < 0.05:
        return {
            "pass": False,
            "level": "warning",
            "msg": f"转换率过低 ({ratio:.1%})，原始 {source_size_kb}KB -> 转换后 {converted_size_kb:.0f}KB",
            "fix": "可能是扫描件（无文本层），尝试 OCR 工具或 Docling"
        }
    if ratio < 0.15:
        return {
            "pass": False,
            "level": "warning",
            "msg": f"转换率偏低 ({ratio:.1%})，可能丢失部分内容",
            "fix": "对比原始文件检查是否有大量表格或图片未转换"
        }
    return {"pass": True}
```

### 参考转换率

| 原始格式 | 正常转换率范围 | 说明 |
|----------|---------------|------|
| PDF (文本型) | 15% - 60% | 纯文字 PDF 转换率较高 |
| PDF (扫描件) | < 5% | 需要 OCR |
| DOCX | 20% - 70% | 取决于格式复杂度 |
| PPTX | 10% - 40% | slide 中图片不计入 |
| XLSX | 30% - 80% | 取决于数据密度 |
| HTML | 15% - 50% | 取决于 CSS/JS 占比 |

## 6. 标题结构验证 (heading_structure)

确认转换结果包含结构化标题，以便后续拆分。

```python
import re

def check_heading_structure(content: str) -> dict:
    headings = re.findall(r"^#{1,6}\s+.+", content, re.MULTILINE)
    if len(headings) == 0:
        # 尝试检测中文章节标题
        cn_headings = re.findall(
            r"^第[一二三四五六七八九十百零\d]+[部章節條]",
            content, re.MULTILINE
        )
        if len(cn_headings) == 0:
            return {
                "pass": False,
                "level": "warning",
                "msg": "未检测到结构化标题（Markdown heading 或中文章节号）",
                "fix": "文件可能缺少标题标记，拆分时将使用固定行数策略"
            }
        return {"pass": True, "heading_count": len(cn_headings), "heading_type": "chinese"}
    return {"pass": True, "heading_count": len(headings), "heading_type": "markdown"}
```

## 批量检查执行

```python
def run_quality_checks(
    content: str,
    file_path: str,
    source_size_kb: int | None = None
) -> list[dict]:
    results = []
    results.append({"check": "line_count", **check_line_count(content)})
    results.append({"check": "encoding", **check_encoding(file_path)})
    results.append({"check": "garbled_cjk", **check_garbled_cjk(content)})
    results.append({"check": "table_integrity", **check_table_integrity(content)})
    if source_size_kb:
        results.append({"check": "content_completeness",
                        **check_content_completeness(source_size_kb, content)})
    results.append({"check": "heading_structure", **check_heading_structure(content)})

    errors = [r for r in results if not r.get("pass") and r.get("level") == "error"]
    warnings = [r for r in results if not r.get("pass") and r.get("level") == "warning"]
    return {
        "all_passed": len(errors) == 0,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "results": results,
    }
```
