# Vault 架构最佳实践

基于 compliance KB 项目经验总结的 Obsidian vault 架构模式。适用于大型结构化知识库（数百至数千笔记规模）。

## 目录结构

### 层级式目录

```
vault/
├── 00-Dashboard/              # 首页和全局视图
│   ├── Homepage.md            # vault 入口 MOC
│   ├── 00-conversion-progress.base
│   └── 01-pending-review.base
├── 信用風險/                   # 分类目录
│   ├── _信用風險 MOC.md       # 分类级 MOC
│   ├── 信用風險管理指引.md     # 主笔记
│   ├── 信用風險管理指引-ch03.md # 拆分子笔记
│   ├── 信用風險管理指引-ch04.md
│   └── 信用風險標準法問答.md
├── 市場風險/
│   ├── _市場風險 MOC.md
│   └── ...
├── 流動性風險/
│   ├── _流動性風險 MOC.md
│   └── ...
├── 作業風險/
│   ├── _作業風險 MOC.md
│   └── ...
├── assets/                    # 图片和附件
│   ├── images/
│   └── originals/             # 原始文件备份（可选）
├── templates/                 # Obsidian 模板
│   ├── note-template.md
│   └── moc-template.md
└── _meta/                     # vault 元数据
    ├── vault_registry.json
    └── topic_aliases.yml
```

### 命名规则

- **分类目录**：使用中文名称，与 frontmatter `category` 字段一致
- **MOC 文件**：以 `_` 前缀 + 分类名 + ` MOC.md`，例如 `_信用風險 MOC.md`
- **主笔记**：使用原始文件名（去扩展名），例如 `信用風險管理指引.md`
- **拆分子笔记**：主笔记名 + `-ch` + 编号，例如 `信用風險管理指引-ch03.md`
- **Dashboard 文件**：数字前缀排序，例如 `00-conversion-progress.base`

## MOC 导航系统

三层 MOC 结构，从全局到局部。

### 第一层：Homepage MOC

Vault 入口，链接所有分类 MOC。

```markdown
---
type: moc
status: linked
tags:
  - MOC
  - homepage
created: 2026-03-22
---

# 合規知識庫

## 風險分類

- [[_信用風險 MOC|信用風險]]
- [[_市場風險 MOC|市場風險]]
- [[_流動性風險 MOC|流動性風險]]
- [[_作業風險 MOC|作業風險]]

## 監管框架

- [[_Basel MOC|Basel 框架]]
- [[_本地法規 MOC|本地法規]]

## 管理面板

- 📊 [[00-conversion-progress.base|转换进度]]
- 📋 [[01-pending-review.base|待审查]]
```

### 第二层：分类 MOC

每个分类目录的索引，列出所有主笔记。

```markdown
---
type: moc
category: "信用風險"
status: linked
tags:
  - MOC
  - 信用風險
created: 2026-03-22
---

# 信用風險

> [!abstract] 分类概述
> 本分类包含信用風險管理相关法規、指引及內部規範。

## 法規指引

- [[信用風險管理指引]] — 主要管理框架
- [[信用風險標準法問答]] — FAQ 汇编

## 内部规范

- [[信用風險評估作業要點]] — 内部评估流程

## 相关主题

- [[_市場風險 MOC|市場風險]] — 交叉风险
- [[_Basel MOC|Basel 框架]] — 上位框架
```

### 第三层：主题 MOC（可选）

跨分类的主题索引，用于横向关联。

```markdown
---
type: moc
tags:
  - MOC
  - Basel
created: 2026-03-22
---

# Basel 框架

## 信用风险相关

- [[信用風險管理指引#第三章|標準法]]
- [[信用風險管理指引#第四章|IRB 法]]

## 市场风险相关

- [[市場風險管理要點#FRTB|FRTB 框架]]
```

## parent 字段与文档层级

`parent` frontmatter 字段构建文档树结构：

```
Homepage MOC
├── _信用風險 MOC          (parent: [[Homepage]])
│   ├── 信用風險管理指引    (parent: [[_信用風險 MOC]])
│   │   ├── ...-ch01       (parent: [[信用風險管理指引]])
│   │   ├── ...-ch02       (parent: [[信用風險管理指引]])
│   │   └── ...-ch03       (parent: [[信用風險管理指引]])
│   └── 信用風險標準法問答  (parent: [[_信用風險 MOC]])
└── _市場風險 MOC          (parent: [[Homepage]])
    └── ...
```

用途：
- Agent 可通过 parent 链向上遍历获取上下文
- Bases 视图可按 parent 分组
- 面包屑导航（配合 Breadcrumbs 插件）

## vault_registry.json

Vault 的全局索引文件，供 agent 快速检索。

### Schema

```json
{
  "version": 1,
  "generated": "2026-03-22T10:00:00Z",
  "notes": [
    {
      "path": "信用風險/信用風險管理指引.md",
      "title": "信用風險管理指引",
      "parent": "_信用風險 MOC",
      "category": "信用風險",
      "type": "regulation",
      "status": "linked",
      "tags": ["信用風險", "Basel/IRB", "資本適足"],
      "summary": "規範銀行信用風險之辨識、衡量、監控及報告要求，涵蓋標準法及內部評等法。",
      "children": [
        "信用風險/信用風險管理指引-ch01.md",
        "信用風險/信用風險管理指引-ch02.md",
        "信用風險/信用風險管理指引-ch03.md"
      ]
    }
  ],
  "categories": [
    {
      "name": "信用風險",
      "moc_path": "信用風險/_信用風險 MOC.md",
      "note_count": 15
    }
  ],
  "stats": {
    "total_notes": 245,
    "total_categories": 8,
    "total_mocs": 12
  }
}
```

### 用途

- Agent 检索：不需要打开每个文件，直接查索引找到相关笔记
- 完整性检查：确认所有文件已索引
- 统计报告：vault 整体状况

### 更新时机

- 每次批量转换后重新生成
- 新增/删除笔记后增量更新
- 可用脚本定期全量重建

## topic_aliases.yml

主题别名映射，解决繁简体中文和英文同义词问题。

```yaml
# topic_aliases.yml
信用風險:
  aliases:
    - 信用风险        # 简体
    - Credit Risk     # 英文
    - credit_risk     # 编程用
  related:
    - 違約風險
    - Default Risk

市場風險:
  aliases:
    - 市场风险
    - Market Risk
    - market_risk
  related:
    - 利率風險
    - 匯率風險

流動性風險:
  aliases:
    - 流动性风险
    - Liquidity Risk
    - liquidity_risk
  related:
    - 資金流動性
    - 市場流動性

資本適足:
  aliases:
    - 资本充足
    - Capital Adequacy
    - CAR
  related:
    - 最低資本要求
    - 資本緩衝

Basel:
  aliases:
    - 巴塞爾
    - 巴塞尔
    - Basel III
    - Basel IV
  related:
    - BIS
    - BCBS
```

### 用途

- Agent 查询时自动扩展同义词
- 搜索 "信用风险"（简体）也能找到 "信用風險"（繁体）笔记
- 构建 wikilink 时选择正确的目标笔记名

## Agent 检索优化

### 检索路径

Agent 查找信息的推荐路径：

1. **先查 vault_registry.json** — 通过 summary 和 tags 定位候选笔记
2. **再查 topic_aliases.yml** — 扩展查询词
3. **读取 MOC 获取结构** — 理解笔记间关系
4. **最后读取具体笔记** — 获取详细内容

### 查询示例

```
用户问: "IRB 法的风险权重怎么计算？"

Agent 路径:
1. vault_registry.json -> tags 含 "Basel/IRB" 的笔记
2. topic_aliases.yml -> "IRB" 相关: 內部評等法, Internal Ratings-Based
3. 读取候选笔记的 parent 链 -> 找到所属章节
4. 读取具体章节内容 -> 回答问题
```

## 批量处理模式

大型 vault 构建采用分阶段执行，避免单次处理量过大。

### Phase 1: 转换 (Convert)

```
输入: 原始文件目录
输出: 每个文件对应的 .md 文件 + frontmatter
状态: status = "raw"
```

- 按分类目录逐批处理
- 每批完成后运行品质检查
- 记录失败文件，不阻塞后续批次

### Phase 2: 拆分 (Split)

```
输入: 超过阈值（如 8000 字符）的 .md 文件
输出: 拆分后的子笔记 + 更新主笔记
状态: status = "split"
```

- 检测文件适用的 splitting pattern
- 生成子笔记，设置 parent 指向主笔记
- 主笔记替换为子笔记链接列表

### Phase 3: 索引 (Index)

```
输入: 所有 .md 文件
输出: vault_registry.json, 各级 MOC
状态: status = "indexed"
```

- 扫描所有笔记的 frontmatter
- 生成 vault_registry.json
- 创建分类 MOC 和 Homepage MOC

### Phase 4: 互联 (Link)

```
输入: vault_registry.json + topic_aliases.yml
输出: 笔记中插入 wikilinks
状态: status = "linked"
```

- 基于 topic_aliases.yml 识别可链接的术语
- 在笔记正文中插入 wikilinks
- 避免过度链接（同一术语每篇笔记只链接首次出现）

### 断点续跑

每个 phase 完成后更新 frontmatter status，下次可从断点继续：

```python
# 找出需要继续的文件
pending_convert = [n for n in registry if n["status"] == "raw"]
pending_split = [n for n in registry if n["status"] == "raw" and n["size_kb"] > threshold]
pending_index = [n for n in registry if n["status"] in ("raw", "split")]
pending_link = [n for n in registry if n["status"] != "linked"]
```
