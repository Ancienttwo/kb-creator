# Obsidian Bases 结构化视图参考

Bases 是 Obsidian 的结构化数据视图功能，可以将 vault 笔记以 table/card/list 形式展示、筛选和排序。kb-creator 使用 Bases 构建知识库的管理面板。

## .base 文件格式

Bases 视图定义存储为 `.base` 文件（YAML 格式），放在 vault 中任意位置。

### 基本结构

```yaml
# example.base
filter:
  operator: and
  conditions: []
formulaColumns: {}
groupBy: []
columns:
  file: { visible: true, width: 250 }
  source_file: { visible: true }
  category: { visible: true }
  status: { visible: true }
  tags: { visible: true }
sort:
  - column: file
    direction: asc
```

## Filter 语法

### 运算符

| 运算符 | 适用类型 | 说明 |
|--------|----------|------|
| `is` | text, number, date | 完全匹配 |
| `is-not` | text, number, date | 不匹配 |
| `contains` | text, list | 包含子串 |
| `does-not-contain` | text, list | 不包含子串 |
| `starts-with` | text | 以...开头 |
| `ends-with` | text | 以...结尾 |
| `is-empty` | all | 字段为空 |
| `is-not-empty` | all | 字段非空 |
| `is-greater-than` | number, date | 大于 |
| `is-less-than` | number, date | 小于 |

### 单条件筛选

```yaml
filter:
  operator: and
  conditions:
    - column: status
      operator: is
      value: raw
```

### 多条件组合（AND）

```yaml
filter:
  operator: and
  conditions:
    - column: category
      operator: is
      value: "信用風險"
    - column: status
      operator: is-not
      value: linked
```

### 多条件组合（OR）

```yaml
filter:
  operator: or
  conditions:
    - column: type
      operator: is
      value: regulation
    - column: type
      operator: is
      value: guideline
```

### 嵌套条件

```yaml
filter:
  operator: and
  conditions:
    - operator: or
      conditions:
        - column: type
          operator: is
          value: regulation
        - column: type
          operator: is
          value: guideline
    - column: status
      operator: is-not
      value: raw
```

## Sort 语法

```yaml
sort:
  - column: category
    direction: asc
  - column: created
    direction: desc
```

支持多级排序，按列出顺序依次排序。

## Group By

```yaml
groupBy:
  - column: category
  - column: status
```

按字段值分组显示，支持多级分组。

## Formula Columns（公式列）

计算列，基于已有字段生成新值。

```yaml
formulaColumns:
  progress_label:
    formula: "if(prop(\"status\") = \"linked\", \"完成\", if(prop(\"status\") = \"reviewed\", \"审查中\", \"待处理\"))"
    type: text
  file_count:
    formula: "length(prop(\"tags\"))"
    type: number
```

### 常用函数

| 函数 | 说明 | 示例 |
|------|------|------|
| `prop("field")` | 读取字段值 | `prop("status")` |
| `if(cond, yes, no)` | 条件判断 | `if(prop("status") = "raw", "待处理", "已处理")` |
| `length(val)` | 列表/字符串长度 | `length(prop("tags"))` |
| `contains(str, sub)` | 包含判断 | `contains(prop("category"), "風險")` |
| `now()` | 当前时间 | `now()` |
| `date(str)` | 解析日期 | `date(prop("created"))` |
| `concat(a, b)` | 字符串拼接 | `concat(prop("category"), " - ", prop("type"))` |

## Column 配置

```yaml
columns:
  file:
    visible: true
    width: 250
  source_file:
    visible: true
    width: 200
  category:
    visible: true
    width: 120
  status:
    visible: true
    width: 100
  tags:
    visible: true
    width: 180
  size_kb:
    visible: false
  created:
    visible: true
    width: 110
```

- `file` 是内置列，显示笔记文件名（带链接）
- 其他列名对应 frontmatter 字段名
- `visible: false` 隐藏列但保留数据可用于筛选

## kb-creator 实用示例

### 转换进度追踪

```yaml
# 00-conversion-progress.base
filter:
  operator: and
  conditions:
    - column: type
      operator: is-not
      value: moc
sort:
  - column: category
    direction: asc
  - column: status
    direction: asc
groupBy:
  - column: category
formulaColumns:
  状态标记:
    formula: "if(prop(\"status\") = \"linked\", \"✅\", if(prop(\"status\") = \"reviewed\", \"🔍\", if(prop(\"status\") = \"indexed\", \"📋\", \"⏳\")))"
    type: text
columns:
  file: { visible: true, width: 280 }
  status: { visible: true, width: 100 }
  状态标记: { visible: true, width: 80 }
  source_file: { visible: true, width: 200 }
  format: { visible: true, width: 80 }
  size_kb: { visible: true, width: 80 }
  created: { visible: true, width: 110 }
```

### 待审查文件视图

```yaml
# 01-pending-review.base
filter:
  operator: and
  conditions:
    - column: status
      operator: is
      value: raw
    - column: type
      operator: is-not
      value: moc
sort:
  - column: size_kb
    direction: desc
columns:
  file: { visible: true, width: 280 }
  category: { visible: true, width: 120 }
  source_file: { visible: true, width: 200 }
  format: { visible: true, width: 80 }
  size_kb: { visible: true, width: 80 }
```

### 分类 MOC 索引

```yaml
# 02-moc-index.base
filter:
  operator: and
  conditions:
    - column: type
      operator: is
      value: moc
sort:
  - column: category
    direction: asc
columns:
  file: { visible: true, width: 280 }
  category: { visible: true, width: 150 }
  status: { visible: true, width: 100 }
  tags: { visible: true, width: 200 }
```

### 法规文件总览

```yaml
# 03-regulations.base
filter:
  operator: or
  conditions:
    - column: type
      operator: is
      value: regulation
    - column: type
      operator: is
      value: guideline
sort:
  - column: category
    direction: asc
  - column: file
    direction: asc
groupBy:
  - column: category
columns:
  file: { visible: true, width: 300 }
  type: { visible: true, width: 100 }
  chapter: { visible: true, width: 200 }
  parent: { visible: true, width: 200 }
  status: { visible: true, width: 100 }
```
