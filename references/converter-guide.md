# 转换工具安装与使用指南

本指南涵盖 kb-creator 支持的文件转换工具。工具按推荐优先级排列。

## 工具概览

| 工具 | 主要用途 | 支持格式 | 安装方式 |
|------|----------|----------|----------|
| markitdown | 通用文件转 Markdown | DOCX, PPTX, XLSX, PDF, HTML, Images | `uv pip install` |
| pdfplumber | PDF 表格提取 | PDF | `uv pip install` |
| pandoc | 通用格式转换（fallback） | DOCX, HTML, EPUB, LaTeX, RST | 系统安装 |
| Docling | 高质量文件理解 | PDF, DOCX, PPTX, HTML | `uv pip install` |

## markitdown

微软开源的文件转 Markdown 工具，覆盖面最广，适合批量转换。

### 安装

```bash
uv pip install markitdown
```

### 使用

```python
from markitdown import MarkItDown

md = MarkItDown()
result = md.convert("input.docx")
print(result.text_content)
```

### 支持格式详情

- **DOCX**: 保留标题层级、列表、表格、粗体/斜体
- **PPTX**: 按 slide 顺序转换，保留标题和正文
- **XLSX**: 每个 sheet 转为 Markdown 表格
- **PDF**: 提取文本层（无 OCR，扫描件需配合其他工具）
- **HTML**: 清理标签转纯 Markdown
- **Images**: 配合 LLM 进行图像描述（需额外配置）

### 限制

- PDF 表格提取质量一般（复杂表格用 pdfplumber）
- 不支持扫描件 OCR
- CJK 文件偶有编码问题，需后处理验证

## pdfplumber

专注 PDF 解析，表格提取能力最强。适合包含大量表格的监管文件。

### 安装

```bash
uv pip install pdfplumber
```

### 使用

```python
import pdfplumber

with pdfplumber.open("input.pdf") as pdf:
    for page in pdf.pages:
        # 提取文本
        text = page.extract_text()
        # 提取表格
        tables = page.extract_tables()
        for table in tables:
            # table 是二维列表，可转 Markdown 表格
            pass
```

### 表格转 Markdown 辅助函数

```python
def table_to_markdown(table: list[list[str]]) -> str:
    if not table or not table[0]:
        return ""
    headers = table[0]
    md = "| " + " | ".join(str(h or "") for h in headers) + " |\n"
    md += "| " + " | ".join("---" for _ in headers) + " |\n"
    for row in table[1:]:
        md += "| " + " | ".join(str(c or "") for c in row) + " |\n"
    return md
```

### 适用场景

- 金融报表、监管附表
- 含合并单元格的复杂表格
- 需要精确坐标的 PDF 布局分析

## pandoc

通用文档转换器，作为 fallback 使用。需系统级安装。

### 安装

```bash
# macOS
brew install pandoc

# Ubuntu/Debian
sudo apt-get install pandoc
```

### 使用

```bash
# DOCX -> Markdown
pandoc input.docx -t markdown -o output.md

# HTML -> Markdown
pandoc input.html -t markdown -o output.md

# 指定 Markdown 变体（推荐 commonmark）
pandoc input.docx -t commonmark -o output.md --wrap=none
```

### 适用场景

- markitdown 转换失败时的 fallback
- EPUB、LaTeX、RST 等 markitdown 不支持的格式
- 需要精细控制输出格式时

## Docling

IBM 开源的高质量文件理解工具，使用 AI 模型进行版面分析。

### 安装

```bash
uv pip install docling
```

### 使用

```python
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("input.pdf")
md_text = result.document.export_to_markdown()
```

### 适用场景

- 复杂版面的 PDF（多栏、图文混排）
- 需要高质量结构化输出
- 学术论文的精确解析

### 限制

- 首次运行需下载模型（约 1-2 GB）
- 转换速度较慢（有 GPU 会快很多）
- 依赖较重

## Agent 消费格式

以下 JSON 结构供 agent 程序化读取，用于自动检测和安装工具。

```json
{
  "converters": [
    {
      "name": "markitdown",
      "install_cmd": "uv pip install markitdown",
      "check_cmd": "python -c \"import markitdown; print(markitdown.__version__)\"",
      "formats": ["docx", "pptx", "xlsx", "pdf", "html", "jpg", "png"],
      "priority": 1,
      "type": "python_package"
    },
    {
      "name": "pdfplumber",
      "install_cmd": "uv pip install pdfplumber",
      "check_cmd": "python -c \"import pdfplumber; print(pdfplumber.__version__)\"",
      "formats": ["pdf"],
      "priority": 2,
      "type": "python_package",
      "note": "PDF 表格提取专用，配合 markitdown 使用"
    },
    {
      "name": "pandoc",
      "install_cmd_macos": "brew install pandoc",
      "install_cmd_linux": "sudo apt-get install -y pandoc",
      "check_cmd": "pandoc --version | head -1",
      "formats": ["docx", "html", "epub", "latex", "rst", "org"],
      "priority": 3,
      "type": "system_package",
      "note": "Fallback 转换器"
    },
    {
      "name": "docling",
      "install_cmd": "uv pip install docling",
      "check_cmd": "python -c \"import docling; print('ok')\"",
      "formats": ["pdf", "docx", "pptx", "html"],
      "priority": 4,
      "type": "python_package",
      "note": "高质量文件理解，依赖较重，需下载模型"
    }
  ],
  "format_to_converter": {
    "pdf": ["markitdown", "pdfplumber", "docling", "pandoc"],
    "docx": ["markitdown", "pandoc", "docling"],
    "pptx": ["markitdown", "docling"],
    "xlsx": ["markitdown"],
    "html": ["markitdown", "pandoc", "docling"],
    "epub": ["pandoc"],
    "csv": ["native"],
    "txt": ["native"],
    "md": ["native"]
  }
}
```

## 转换策略

1. **优先用 markitdown** — 速度快、覆盖广
2. **PDF 表格用 pdfplumber** — 检测到 PDF 含表格时自动切换
3. **markitdown 失败则 pandoc fallback** — 格式不支持或转换异常时
4. **高质量需求用 Docling** — 用户明确要求或自动检测到复杂版面时
5. **原生处理** — `md`, `txt`, `csv` 直接读取，无需转换工具
