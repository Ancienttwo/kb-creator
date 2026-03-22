# Frontmatter Schema 定义

Vault 笔记的 YAML frontmatter 字段定义。所有笔记必须包含 frontmatter 以支持 Obsidian 属性面板、Bases 视图筛选和 agent 检索。

## 字段一览

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `source_file` | string | 是 | - | 原始文件名（含扩展名） |
| `format` | string | 是 | - | 原始格式：`pdf`, `docx`, `xlsx`, `pptx`, `html`, `md` |
| `size_kb` | number | 否 | - | 原始文件大小（KB，四舍五入取整） |
| `category` | string | 是 | - | 所属分类目录名 |
| `chapter` | string | 否 | - | 拆分来源章节标题（仅拆分产生的子笔记） |
| `parent` | string | 否 | - | 父笔记的 wikilink，格式 `[[父笔记名]]` |
| `type` | string | 是 | `note` | 笔记类型，见下方枚举 |
| `status` | string | 是 | `raw` | 处理状态，见下方枚举 |
| `tags` | list | 否 | `[]` | 标签列表 |
| `created` | date | 是 | 转换日期 | ISO 8601 格式 `YYYY-MM-DD` |

## 字段详细定义

### source_file

原始来源文件名，保留扩展名。用于溯源和去重。

```yaml
source_file: "信用風險管理指引_v3.pdf"
```

### format

原始文件格式，小写。

允许值：`pdf`, `docx`, `xlsx`, `pptx`, `html`, `md`, `txt`, `csv`, `rtf`

```yaml
format: pdf
```

### size_kb

原始文件大小，单位 KB。用于转换品质检查（比对转换前后大小比）。

```yaml
size_kb: 2450
```

### category

Vault 中的分类目录名称。对应 vault 根目录下的文件夹。

```yaml
category: "信用風險"
```

### chapter

仅当笔记由长文件拆分产生时使用。记录该笔记对应的原始章节。

```yaml
chapter: "第三章 信用風險標準法"
```

### parent

文档层级中的父节点，使用 Obsidian wikilink 语法。用于构建文档树和 MOC 导航。

- 拆分子笔记的 parent 指向拆分前的主笔记
- 主笔记的 parent 指向所属分类的 MOC

```yaml
parent: "[[信用風險管理指引]]"
```

### type

笔记类型枚举：

| 值 | 说明 |
|----|------|
| `note` | 常规笔记（默认） |
| `moc` | Map of Content 导航笔记 |
| `regulation` | 法规/监管文件 |
| `guideline` | 指引/规范 |
| `policy` | 内部政策 |
| `procedure` | 作业流程 |
| `form` | 表单/范本 |
| `reference` | 参考资料 |
| `glossary` | 名词定义/术语表 |

```yaml
type: regulation
```

### status

处理状态枚举：

| 值 | 说明 |
|----|------|
| `raw` | 刚转换完成，未经审查（默认） |
| `reviewed` | 已人工审查内容正确性 |
| `split` | 已完成拆分 |
| `indexed` | 已加入 vault_registry.json |
| `linked` | 已完成内部 wikilink 互联 |

```yaml
status: raw
```

### tags

标签列表，支持嵌套标签。

```yaml
tags:
  - 信用風險
  - Basel/IRB
  - 資本適足
```

### created

笔记创建日期，ISO 8601 格式。默认使用转换执行日期。

```yaml
created: 2026-03-22
```

## 完整示例

### 主笔记（未拆分）

```yaml
---
source_file: "流動性風險管理要點.pdf"
format: pdf
size_kb: 890
category: "流動性風險"
parent: "[[流動性風險 MOC]]"
type: guideline
status: raw
tags:
  - 流動性風險
  - LCR
  - NSFR
created: 2026-03-22
---
```

### 拆分子笔记

```yaml
---
source_file: "信用風險管理指引_v3.pdf"
format: pdf
size_kb: 2450
category: "信用風險"
chapter: "第三章 信用風險標準法"
parent: "[[信用風險管理指引]]"
type: regulation
status: split
tags:
  - 信用風險
  - 標準法
  - 風險權數
created: 2026-03-22
---
```

### MOC 笔记

```yaml
---
type: moc
category: "信用風險"
status: linked
tags:
  - MOC
  - 信用風險
created: 2026-03-22
---
```
