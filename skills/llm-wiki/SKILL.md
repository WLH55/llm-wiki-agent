---
name: llm-wiki
description: >
  LLM Wiki Agent 共享基础技能。提供配置解析协议、wiki 结构速查、frontmatter 规范、
  命名规范、工具脚本参考、wikilink 格式、日志格式。所有其他 wiki 技能（wiki-query、
  wiki-update、wiki-switch、wiki-setup）都依赖此技能进行配置解析。
---

# LLM Wiki — 共享基础

你正在与 LLM Wiki 知识库交互。本技能定义了所有 wiki 操作共用的协议。
每个 wiki 技能在执行任何操作之前，必须先通过本协议解析配置。

## 配置解析协议

按以下优先级解析 `LLM_WIKI_PATH`：

### 第一步：项目级 .env（最高优先级）

从当前工作目录向上遍历，逐级检查每个父目录中是否存在 `.env` 文件。
如果找到且包含 `LLM_WIKI_PATH=<值>`，则使用该值。

```bash
# 示例：D:/projects/my-app/.env
LLM_WIKI_PATH=D:/AI/my-special-wiki
```

此值存储为本次会话的 `$LLM_WIKI_PATH`。

### 第二步：全局配置（回退）

读取 `~/.llm-wiki/active` 获取当前活跃的配置名（如 `primary`）。
然后读取 `~/.llm-wiki/config.<名称>` 获取 `LLM_WIKI_PATH`。

```bash
# ~/.llm-wiki/active（包含一个单词）
primary

# ~/.llm-wiki/config.primary
LLM_WIKI_PATH=D:/AI/llm-wiki-agent
LLM_WIKI_LINK_FORMAT=wikilink
```

### 第三步：未配置

如果 `.env` 和 `~/.llm-wiki/` 都不存在，告知用户：

> 尚未配置知识库。请运行 `wiki-setup` 初始化，或在此项目中创建 `.env` 文件，
> 内容为 `LLM_WIKI_PATH=<知识库路径>`。

然后停止。未解析到 `LLM_WIKI_PATH` 之前，不要继续执行。

### 解析后的变量

| 变量 | 来源 | 默认值 | 说明 |
|---|---|---|---|
| `LLM_WIKI_PATH` | .env 或 config | *(必填)* | wiki 项目根目录的绝对路径 |
| `LLM_WIKI_LINK_FORMAT` | config | `wikilink` | 链接格式：`wikilink` 或 `markdown` |

---

## Wiki 结构速查

知识库存放于 `$LLM_WIKI_PATH/wiki/`，目录布局如下：

```
wiki/
├── index.md          ← 目录索引（无 frontmatter，系统页面）
├── overview.md       ← 动态综合摘要（无 frontmatter，系统页面）
├── log.md            ← 操作日志（无 frontmatter，系统页面）
├── sources/          ← 源文档摘要页（kebab-case.md）
├── entities/         ← 人物、公司、项目、工具（TitleCase.md）
├── concepts/         ← 想法、框架、方法论（TitleCase.md）
└── syntheses/        ← 已保存的查询答案（kebab-case.md）
```

系统页面（`index.md`、`overview.md`、`log.md`、`lint-report.md`）不使用 YAML frontmatter。

## Frontmatter 规范

每个非系统 wiki 页面必须以 YAML frontmatter 开头。按类型必填字段：

### source（来源页）

```yaml
---
title: "源文档标题"
type: source
tags: []
date: YYYY-MM-DD
source_file: raw/...
---
```

必填：`title`、`type`、`tags`、`date`、`source_file`

标准章节：`## 摘要`、`## 核心论点`、`## 重要引述`、`## 关联`、`## 矛盾`

### entity（实体页）

```yaml
---
title: "实体名称"
type: entity
tags: []
sources: []
last_updated: YYYY-MM-DD
---
```

必填：`title`、`type`、`tags`、`sources`、`last_updated`

标准章节：`# 实体名称`（一句话定义）、`## 关联`

### concept（概念页）

```yaml
---
title: "概念名称"
type: concept
tags: []
sources: []
last_updated: YYYY-MM-DD
---
```

必填：`title`、`type`、`tags`、`sources`、`last_updated`

标准章节：`# 概念名称`（一句话定义）、`## 关联`

### synthesis（综合页）

```yaml
---
title: "综合标题"
type: synthesis
tags: []
sources: []
last_updated: YYYY-MM-DD
---
```

必填：`title`、`type`、`tags`、`sources`、`last_updated`

标准章节：`# 综合标题`（对问题的综合回答）

### 领域专用模板

日记/日志来源使用 `tags: [diary]`，章节：`## 事件摘要`、`## 关键决定`、`## 精力与情绪`、`## 关联`、`## 变化与矛盾`。

会议记录使用 `tags: [meeting]`，章节：`## 目标`、`## 关键讨论`、`## 做出的决定`、`## 行动项`。

## 命名规范

| 页面类型 | 目录 | 文件名 | 示例 |
|---|---|---|---|
| 来源 | `wiki/sources/` | `kebab-case.md` | `my-article.md` |
| 实体 | `wiki/entities/` | `TitleCase.md` | `OpenAI.md` |
| 概念 | `wiki/concepts/` | `TitleCase.md` | `ReinforcementLearning.md` |
| 综合 | `wiki/syntheses/` | `kebab-case.md` | `transformer-applications.md` |

**重要**：来源页的 slug 必须严格与原始文件主名匹配（小写、连字符）。
例如 `raw/articles/My Article.md` → `wiki/sources/my-article.md`。
严禁根据文章标题或内容自行翻译或生造 slug。

## 工具脚本速查

所有工具位于 `$LLM_WIKI_PATH/tools/`。仅执行机械操作，不调用 LLM。

| 工具 | 用途 | 主要参数 |
|---|---|---|
| `python tools/query.py "<问题>"` | 关键词匹配 wiki 页面，输出路径 | — |
| `python tools/ingest.py --validate-only` | 验证 wiki 完整性（断链、未索引页面） | `--validate-only` |
| `python tools/lint.py` | 结构健康检查（孤立页、断链、frontmatter、图谱） | `--save` |
| `python tools/build_graph.py` | 构建知识图谱（节点 + 边 → graph.json + graph.html） | `--open`、`--report` |
| `python tools/check_stale.py` | 通过 SHA-256 哈希对比检测过期来源 | `--scan`、`--json`、`--update`、`--update-file`、`--force` |
| `python tools/refresh.py` | 列出过期来源页面 | `--force`、`--dry-run` |
| `python tools/pdf2md.py <arxiv-id 或 pdf>` | 将 PDF/arXiv 转为 Markdown | `--backend`、`-o` |
| `python tools/file_to_markdown.py <目录>` | 批量将非 md 文件转为 Markdown | `--input_dir`、`--delete_source` |

Python 要求：`>=3.10, <3.14`。工具脚本不依赖 litellm 或 API 密钥。

## Wikilink 格式

使用 `[[页面名称]]` 语法进行交叉引用。页面名称为去掉 `.md` 扩展名的文件名。

- 解析时不区分大小写（如 `[[openai]]` 可解析到 `entities/OpenAI.md`）
- 不要在 wikilink 中包含目录前缀（写 `[[OpenAI]]`，不要写 `[[entities/OpenAI]]`）
- 对于矛盾信息，在来源页的 `## 矛盾` 章节中记录

## 图谱系统

知识图谱位于 `$LLM_WIKI_PATH/graph/`：

| 文件 | 说明 |
|---|---|
| `graph/graph.json` | 节点 + 边数据（由 build_graph.py 生成） |
| `graph/graph.html` | 交互式 vis.js 可视化 |
| `graph/.refresh_cache.json` | raw → wiki 过期检测的 SHA-256 哈希缓存 |

边类型：
- `EXTRACTED` — 来自 `[[wikilinks]]`，置信度 1.0
- `INFERRED` — Claude 语义推断，置信度 >= 0.7
- `AMBIGUOUS` — 低置信度推断，置信度 < 0.7

## 索引格式

`wiki/index.md` 遵循以下结构：

```markdown
# Wiki 索引

## 概览
- [概览](overview.md) — 动态综合

## 来源
- [来源标题](sources/slug.md) — 一句话摘要

## 实体
- [实体名称](entities/EntityName.md) — 一句话描述

## 概念
- [概念名称](concepts/ConceptName.md) — 一句话描述

## 综合
- [分析标题](syntheses/slug.md) — 回答的问题
```

## 日志格式

每条记录以 `## [YYYY-MM-DD] <操作> | <标题>` 开头，方便 grep 解析：

```
grep "^## \[" wiki/log.md | tail -10
```

操作类型：`ingest`、`query`、`lint`、`graph`、`refresh`、`update`、`setup`、`switch`
