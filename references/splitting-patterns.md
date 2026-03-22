# 文件拆分边界模式 (Splitting Boundary Patterns)

根据文件类型和语言，使用以下 regex 模式识别拆分边界。每个模式包含：正则表达式、优先级（1 最高）、类型标签、示例文本。

## 中文法规/监管文件

适用于台湾金融监管文件、法规条文、银行内部规范等。

| 优先级 | 类型标签 | Regex | 说明 | 示例 |
|--------|----------|-------|------|------|
| 1 | `part` | `^第[一二三四五六七八九十百零\d]+部[分]?\s` | 部级标题 | `第一部 總則` |
| 2 | `chapter` | `^第[一二三四五六七八九十百零\d]+章\s` | 章级标题 | `第三章 風險管理` |
| 3 | `section` | `^第[一二三四五六七八九十百零\d]+節\s` | 节级标题 | `第二節 信用風險` |
| 4 | `article` | `^第[一二三四五六七八九十百零\d]+條` | 条文 | `第十五條 銀行應建立…` |
| 5 | `appendix_table` | `^附表[一二三四五六七八九十\d]*` | 附表 | `附表一 資本適足率計算` |
| 5 | `appendix_doc` | `^附錄[一二三四五六七八九十\d]*` | 附录 | `附錄二 名詞定義` |
| 3 | `ref_code_LD` | `^LD-[A-Z0-9]+-\d+` | LD 编号文件 | `LD-B-0015 流動性風險` |
| 3 | `ref_code_GL` | `^GL-[A-Z0-9]+-\d+` | GL 编号文件 | `GL-C-0023 合規指引` |

### 完整 Regex（可直接用于 Python re 模块）

```python
CHINESE_REGULATORY_PATTERNS = [
    {
        "regex": r"^第[一二三四五六七八九十百零\d]+部[分]?\s",
        "priority": 1,
        "type": "part",
        "label": "部"
    },
    {
        "regex": r"^第[一二三四五六七八九十百零\d]+章\s",
        "priority": 2,
        "type": "chapter",
        "label": "章"
    },
    {
        "regex": r"^第[一二三四五六七八九十百零\d]+節\s",
        "priority": 3,
        "type": "section",
        "label": "節"
    },
    {
        "regex": r"^第[一二三四五六七八九十百零\d]+條",
        "priority": 4,
        "type": "article",
        "label": "條"
    },
    {
        "regex": r"^附表[一二三四五六七八九十\d]*",
        "priority": 5,
        "type": "appendix_table",
        "label": "附表"
    },
    {
        "regex": r"^附錄[一二三四五六七八九十\d]*",
        "priority": 5,
        "type": "appendix_doc",
        "label": "附錄"
    },
    {
        "regex": r"^LD-[A-Z0-9]+-\d+",
        "priority": 3,
        "type": "ref_code_LD",
        "label": "LD 编号"
    },
    {
        "regex": r"^GL-[A-Z0-9]+-\d+",
        "priority": 3,
        "type": "ref_code_GL",
        "label": "GL 编号"
    },
]
```

## 英文技术文档

适用于技术规范、RFC、白皮书等。

| 优先级 | 类型标签 | Regex | 说明 | 示例 |
|--------|----------|-------|------|------|
| 1 | `part` | `^Part\s+(\d+\|[IVXLC]+)[.:\s]` | Part 级别 | `Part 3: Implementation` |
| 2 | `chapter` | `^Chapter\s+(\d+\|[IVXLC]+)[.:\s]` | Chapter 级别 | `Chapter 5: Risk Framework` |
| 3 | `section` | `^Section\s+\d+(\.\d+)*[.:\s]` | Section 编号 | `Section 3.2.1 Capital Requirements` |
| 4 | `numbered` | `^\d+(\.\d+)+\s+[A-Z]` | 数字编号标题 | `3.2.1 Capital Buffer` |
| 5 | `appendix` | `^Appendix\s+[A-Z\d]+[.:\s]` | Appendix | `Appendix B: Glossary` |
| 5 | `annex` | `^Annex\s+[A-Z\d]+[.:\s]` | Annex | `Annex 1: Data Tables` |
| 5 | `schedule` | `^Schedule\s+[A-Z\d]+[.:\s]` | Schedule | `Schedule A: Fee Table` |

```python
ENGLISH_TECHNICAL_PATTERNS = [
    {
        "regex": r"^Part\s+(\d+|[IVXLC]+)[.:\s]",
        "priority": 1,
        "type": "part",
        "label": "Part"
    },
    {
        "regex": r"^Chapter\s+(\d+|[IVXLC]+)[.:\s]",
        "priority": 2,
        "type": "chapter",
        "label": "Chapter"
    },
    {
        "regex": r"^Section\s+\d+(\.\d+)*[.:\s]",
        "priority": 3,
        "type": "section",
        "label": "Section"
    },
    {
        "regex": r"^\d+(\.\d+)+\s+[A-Z]",
        "priority": 4,
        "type": "numbered",
        "label": "Numbered heading"
    },
    {
        "regex": r"^Appendix\s+[A-Z\d]+[.:\s]",
        "priority": 5,
        "type": "appendix",
        "label": "Appendix"
    },
    {
        "regex": r"^Annex\s+[A-Z\d]+[.:\s]",
        "priority": 5,
        "type": "annex",
        "label": "Annex"
    },
    {
        "regex": r"^Schedule\s+[A-Z\d]+[.:\s]",
        "priority": 5,
        "type": "schedule",
        "label": "Schedule"
    },
]
```

## 学术论文

适用于 journal article、会议论文、研究报告。

| 优先级 | 类型标签 | Regex | 示例 |
|--------|----------|-------|------|
| 1 | `abstract` | `^(Abstract\|摘要)[:\s]?` | `Abstract` |
| 2 | `introduction` | `^(\d+\.?\s+)?(Introduction\|引言\|前言\|緒論)` | `1. Introduction` |
| 2 | `lit_review` | `^(\d+\.?\s+)?(Literature Review\|Related Work\|文獻回顧)` | `2. Literature Review` |
| 2 | `methodology` | `^(\d+\.?\s+)?(Methodology\|Methods\|研究方法)` | `3. Methodology` |
| 2 | `results` | `^(\d+\.?\s+)?(Results\|Findings\|研究結果)` | `4. Results` |
| 2 | `discussion` | `^(\d+\.?\s+)?(Discussion\|討論)` | `5. Discussion` |
| 2 | `conclusion` | `^(\d+\.?\s+)?(Conclusion[s]?\|結論)` | `6. Conclusions` |
| 3 | `references` | `^(References\|Bibliography\|參考文獻)` | `References` |
| 3 | `acknowledgments` | `^(Acknowledgments?\|致謝)` | `Acknowledgments` |

```python
ACADEMIC_PATTERNS = [
    {"regex": r"^(Abstract|摘要)[:\s]?", "priority": 1, "type": "abstract"},
    {"regex": r"^(\d+\.?\s+)?(Introduction|引言|前言|緒論)", "priority": 2, "type": "introduction"},
    {"regex": r"^(\d+\.?\s+)?(Literature Review|Related Work|文獻回顧)", "priority": 2, "type": "lit_review"},
    {"regex": r"^(\d+\.?\s+)?(Methodology|Methods|研究方法)", "priority": 2, "type": "methodology"},
    {"regex": r"^(\d+\.?\s+)?(Results|Findings|研究結果)", "priority": 2, "type": "results"},
    {"regex": r"^(\d+\.?\s+)?(Discussion|討論)", "priority": 2, "type": "discussion"},
    {"regex": r"^(\d+\.?\s+)?(Conclusion[s]?|結論)", "priority": 2, "type": "conclusion"},
    {"regex": r"^(References|Bibliography|參考文獻)", "priority": 3, "type": "references"},
    {"regex": r"^(Acknowledgments?|致謝)", "priority": 3, "type": "acknowledgments"},
]
```

## 通用 Markdown 标题

适用于所有 Markdown 格式文件的 fallback 拆分。

| 优先级 | 类型标签 | Regex | 示例 |
|--------|----------|-------|------|
| 1 | `h1` | `^# (?!#)` | `# 总则` |
| 2 | `h2` | `^## (?!#)` | `## 信用风险` |
| 3 | `h3` | `^### (?!#)` | `### 计算方法` |
| 4 | `h4` | `^#### (?!#)` | `#### 参数定义` |
| 10 | `hr` | `^(-{3,}\|_{3,}\|\*{3,})\s*$` | `---` |

```python
MARKDOWN_PATTERNS = [
    {"regex": r"^# (?!#)", "priority": 1, "type": "h1"},
    {"regex": r"^## (?!#)", "priority": 2, "type": "h2"},
    {"regex": r"^### (?!#)", "priority": 3, "type": "h3"},
    {"regex": r"^#### (?!#)", "priority": 4, "type": "h4"},
    {"regex": r"^(-{3,}|_{3,}|\*{3,})\s*$", "priority": 10, "type": "hr"},
]
```

## 模式选择策略

1. **自动检测**：扫描文件前 100 行，统计各模式命中次数，选择命中最多的模式集
2. **组合使用**：中文法规模式可与 Markdown 模式叠加（法规模式优先）
3. **Fallback 链**：专用模式 -> Markdown 标题 -> 固定行数拆分（每 500 行）
4. **最小块大小**：拆分后每块不应少于 200 字符（避免过度碎片化）
5. **最大块大小**：单块超过 8000 字符时，降级到次优先级模式继续拆分
