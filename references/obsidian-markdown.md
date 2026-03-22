# Obsidian Flavored Markdown 参考

Obsidian 使用扩展的 Markdown 语法。以下为 kb-creator 生成 vault 笔记时需要遵循的语法规范。

## Wikilinks

Obsidian 的核心链接语法，用于笔记间互联。

### 基本链接

```markdown
[[笔记名称]]
```

链接到 vault 中名为 `笔记名称.md` 的文件。不需要路径，Obsidian 自动解析。

### 别名链接

```markdown
[[笔记名称|显示文本]]
```

链接到 `笔记名称.md`，但显示为 `显示文本`。常用于：
- 简化长标题：`[[信用風險管理指引第三版|信用風險指引]]`
- 语言切换：`[[Credit Risk|信用風險]]`

### 标题链接

```markdown
[[笔记名称#标题名]]
[[笔记名称#标题名|显示文本]]
```

链接到笔记中的特定标题。

### 块引用链接

```markdown
[[笔记名称#^block-id]]
```

链接到笔记中标记了 `^block-id` 的特定段落。

## Embeds（嵌入）

使用 `!` 前缀将其他笔记或资源内联嵌入当前笔记。

### 嵌入笔记

```markdown
![[笔记名称]]
```

将整个笔记内容嵌入当前位置。适合在 MOC 中展示摘要。

### 嵌入笔记特定标题

```markdown
![[笔记名称#标题名]]
```

仅嵌入该标题下的内容。

### 嵌入图片

```markdown
![[image.png]]
![[image.png|300]]
```

嵌入图片，可选指定宽度（像素）。

### 嵌入 PDF

```markdown
![[document.pdf#page=5]]
```

嵌入 PDF 的特定页面。

## Callouts

使用 blockquote 语法创建高亮信息框。

### 基本语法

```markdown
> [!type] 可选标题
> 内容文字
```

### 常用类型

| 类型 | 用途 | 别名 |
|------|------|------|
| `note` | 一般备注 | - |
| `tip` | 提示建议 | `hint`, `important` |
| `warning` | 警告注意 | `caution`, `attention` |
| `info` | 信息说明 | - |
| `abstract` | 摘要概述 | `summary`, `tldr` |
| `todo` | 待办事项 | - |
| `success` | 成功完成 | `check`, `done` |
| `failure` | 失败错误 | `fail`, `missing` |
| `danger` | 危险警示 | `error` |
| `bug` | 已知问题 | - |
| `example` | 示例展示 | - |
| `quote` | 引用出处 | `cite` |
| `question` | 问题疑点 | `help`, `faq` |

### 可折叠 Callout

```markdown
> [!tip]+ 展开的提示（默认展开）
> 内容

> [!warning]- 折叠的警告（默认折叠）
> 内容
```

### kb-creator 推荐用法

```markdown
> [!tldr] 文件摘要
> 本文件为信用風險管理指引第三版，規範銀行信用風險之辨識、衡量、監控及報告要求。

> [!warning] 转换品质提醒
> 本文件由 PDF 自动转换，部分表格可能有格式偏差，请对照原始文件确认。

> [!info] 监管沿革
> 本指引取代 2020 年版本，主要变更包括…
```

## Tags（标签）

### 内联标签

```markdown
这是一个关于 #信用風險 的笔记。
```

### 嵌套标签

```markdown
#風險/信用風險
#風險/市場風險
#Basel/IRB
#Basel/標準法
```

嵌套标签在 Obsidian 中形成树状结构，搜索父标签会包含所有子标签。

### Frontmatter 标签

```yaml
---
tags:
  - 信用風險
  - Basel/IRB
---
```

Frontmatter 中的标签不需要 `#` 前缀。

## Frontmatter Properties

Obsidian 原生支持 YAML frontmatter 作为笔记属性。

```yaml
---
key: value
list:
  - item1
  - item2
date: 2026-03-22
---
```

- 必须在文件最开头
- 用 `---` 包裹
- Obsidian 属性面板可视化编辑
- 支持类型：text, list, number, checkbox, date, datetime

详见 `frontmatter-schema.md` 获取 kb-creator 字段定义。

## Code Blocks

### 行内代码

```markdown
使用 `pip install markitdown` 安装。
```

### 围栏代码块

````markdown
```python
import pdfplumber
```
````

### 支持的语言标识

常用：`python`, `javascript`, `typescript`, `bash`, `json`, `yaml`, `sql`, `markdown`, `html`, `css`

## 数学公式

### 行内公式

```markdown
风险权重公式为 $RW = LGD \times N[(1-R)^{-0.5} \times G(PD)]$。
```

### 块级公式

```markdown
$$
EAD = \sum_{i=1}^{n} exposure_i \times CCF_i
$$
```

Obsidian 使用 MathJax 渲染 LaTeX 语法。

## 脚注

```markdown
信用風險資本計提依據 Basel III 框架[^1]。

[^1]: Basel Committee on Banking Supervision, "Basel III: Finalising post-crisis reforms", December 2017.
```

## 注释

```markdown
这段文字会显示。
%%这段文字是注释，只在编辑模式可见%%
```

## 列表

### 任务列表

```markdown
- [ ] 转换 PDF 文件
- [x] 建立 frontmatter schema
- [ ] 生成 MOC
```

### 有序列表缩进

```markdown
1. 第一层
   1. 第二层
      1. 第三层
```

## 生成笔记时的最佳实践

1. **标题层级**：从 `#` 开始，不跳级（`#` -> `##` -> `###`）
2. **Wikilink 偏好**：优先使用 wikilink `[[]]` 而非标准 Markdown link `[]()`
3. **中文标点**：正文使用全角标点，代码和路径使用半角
4. **空行**：标题前后各留一个空行
5. **表格**：使用 Markdown 表格语法，避免 HTML table
6. **图片路径**：使用 wikilink embed `![[img.png]]`，图片统一存放在 `assets/` 目录
