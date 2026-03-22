# Changelog

## [0.1.1] - 2026-03-22

### Fixed

- `check_deps()` 在 markitdown 缺失时返回 `ok: true`，导致 Skill 跳过安装步骤
- markitdown 检测和调用使用 `shutil.which()` / PATH，无法发现 venv 内安装的包；改为 `sys.executable -m markitdown`
- Artifact 名称不匹配：scanner 落盘 `scan_manifest`、converter 落盘 `convert_batch_detail`，但 SKILL.md 引用 `scan_report` / `convert_report`；统一为后者
- Scanner `os.walk()` 未忽略 `.venv`、`.git`、`node_modules` 等目录，扫描结果被工具链文件污染
- `kb-summary --format frontmatter` 对无 frontmatter 的笔记不修改文件但仍计为 `injected`
- SKILL.md 中 `--check-deps` 调用多传了无用的 dummy 参数

### Added

- 10 个回归测试覆盖上述修复（测试总数 14 → 24）
- Scanner 新增 `IGNORE_DIRS` 常量，默认跳过 14 种工具链/缓存目录

## [0.1.0] - 2026-03-22

### Added

- 项目初始结构：`src/kb_creator/` Python 包 + `bin/` CLI 薄包装
- Agent-First 架构：所有 CLI stdout 只输出 JSON，日志走 stderr，非零退出码仅用于不可恢复错误
- 统一 JSON 契约 (`contracts.py`)：`ok` / `action` / `inputs` / `outputs` / `warnings` / `errors` / `artifacts`
- 6 个 CLI 工具：
  - `kb-scan` — 源目录扫描分析（支持 PDF/DOCX/PPTX/XLSX/CSV/HTML/TXT/MD）
  - `kb-convert` — 转换编排（markitdown + pdfplumber 表格增强 + 依赖检测）
  - `kb-split` — 文档拆分引擎（可配置正则边界 + min/max 行数启发式）
  - `kb-link` — Wiki 链接注入（结构链接 + 语义链接 + MOC 生成 + dry-run）
  - `kb-summary` — 摘要提取/注入（`--extract` 提取候选，`--inject` 写回 callout/frontmatter）
  - `kb-registry` — Vault 注册表生成（`vault_registry.json`）
- `.kb-state.json` 增量恢复机制
- SKILL.md 全流程编排（Phase 0-5：环境检测 → 转换 → 结构化 → 链接 → 摘要 → Obsidian 视图）
- 7 份参考文档：拆分模式库 / frontmatter 定义 / 转换指南 / 质量检查 / Obsidian MD / Bases / Vault 架构
- 6 个模板：frontmatter / MOC / 主题 MOC / 进度仪表板 / Base 视图 / 主题同义词
- 14 个测试（contracts / splitter / state）
