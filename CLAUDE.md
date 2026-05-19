# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指导。

## 项目概述

LLM Wiki Agent 是一个知识管理工作流。将源文档放入 `raw/` 目录，代理会读取文档、提取知识，并维护一个持久互联的 Markdown 知识库。

## 当前入口

- 本地斜杠命令定义在 `.claude/commands/`：`/wiki-ingest`、`/wiki-lint`、`/wiki-graph`、`/wiki-refresh`、`/wiki-setup`
- 全局 skill 定义在 `skills/`：`llm-wiki`、`wiki-query`、`wiki-update`、`wiki-switch`、`wiki-setup`
- `wiki-query`、`wiki-update`、`wiki-switch` 依赖全局 skill，不是仓库内本地斜杠命令
- 详细执行细节以 `skills/` 和 `.claude/commands/` 为准；本文件负责统一规则和页面格式

## 配置解析

所有需要 `LLM_WIKI_PATH` 的流程都按同一优先级解析：

1. 从当前工作目录向上查找 `.env` 中的 `LLM_WIKI_PATH`
2. 如果未找到，读取 `~/.llm-wiki/active`，再读取 `~/.llm-wiki/config.<名称>`

补充规则：

- `wiki-switch` 切换时先更新全局 `active`，再同步更新当前项目命中的 `.env`
- 未解析到 `LLM_WIKI_PATH` 时，停止并提示运行 `wiki-setup` 或创建 `.env`

## 常用工具脚本

```bash
python tools/ingest.py --validate-only      # 验证 wiki 完整性
python tools/query.py "主要主题有哪些？"      # 关键词匹配候选页面
python tools/lint.py                        # 结构健康检查
python tools/build_graph.py                 # 构建图谱
python tools/check_stale.py --scan          # 检测 raw/ 的新增/更新/删除
python tools/check_stale.py                 # 检测已导入来源是否过期
python tools/check_stale.py --update        # 刷新完成后更新哈希缓存
python tools/refresh.py                     # 仅列出过期来源，实际刷新由代理执行
python tools/pdf2md.py paper.pdf            # PDF/arXiv 转 Markdown
python tools/file_to_markdown.py <输入目录>  # 批量转换非 md 文件
```

要求 Python `>=3.10, <3.14`。

## 页面规则

- 系统页面 `wiki/index.md`、`wiki/overview.md`、`wiki/log.md`、`wiki/lint-report.md` 不使用 frontmatter
- 其他所有 wiki 页面都必须以 YAML frontmatter 开头
- 页面间统一使用 `[[PageName]]` 进行交叉引用
- 新信息优先合并到已有页面，不创建重复页面

### 源页面格式

```markdown
---
title: "源文档标题"
type: source
tags: []
date: YYYY-MM-DD
source_file: raw/...
---

## 摘要

## 核心论点

## 重要引述

## 关联

## 矛盾
```

### 实体页面格式

```markdown
---
title: "实体名称"
type: entity
tags: []
sources: []
last_updated: YYYY-MM-DD
---

# 实体名称

一句话定义。

## 关联
```

### 概念页面格式

```markdown
---
title: "概念名称"
type: concept
tags: []
sources: []
last_updated: YYYY-MM-DD
---

# 概念名称

一句话定义。

## 关联
```

### 综合页面格式

```markdown
---
title: "综合标题"
type: synthesis
tags: []
sources: []
last_updated: YYYY-MM-DD
---

# 综合标题

对问题的综合回答。
```

## 导入工作流

- `/wiki-ingest <路径>` 走单文件模式；`/wiki-ingest` 无参数时走批量模式
- 单文件导入前先运行 `python tools/check_stale.py --scan --json` 做变更检测；未变更则跳过
- 写入 `wiki/sources/` 之前，必须按 `source_file` 去重；同一个 raw 文件禁止生成两个来源页
- 导入时更新 `wiki/index.md`、`wiki/overview.md`、相关实体页、相关概念页、`wiki/log.md`
- 导入成功后运行 `python tools/check_stale.py --update-file <raw_path>` 写入哈希缓存
- 批量模式还需要处理 `deleted` 文件，并询问是否删除对应来源页和索引条目
- 收尾运行 `python tools/ingest.py --validate-only`

## 查询工作流

- 通过全局 `wiki-query` skill 执行
- 先按配置规则解析 `$LLM_WIKI_PATH`
- 先读 `wiki/index.md` 和 `wiki/overview.md`
- 检索顺序固定为：索引和 frontmatter 快查 -> `python tools/query.py` -> 分段 grep -> 完整读取
- 回答必须使用 `[[PageName]]` 引用，并列出来源页面
- 若用户同意保存为 synthesis：写入 `wiki/syntheses/`、更新 `index.md` / `overview.md` / `log.md`、补齐缺失实体或概念页、运行 `python tools/build_graph.py` 和 `python tools/ingest.py --validate-only`

## 更新工作流

- 通过全局 `wiki-update` skill 执行
- 从当前项目提炼值得长期保留的知识，不复制代码和文件列表
- 优先合并已有实体页和概念页，不创建重复页
- 更新 `wiki/index.md`、`wiki/overview.md`、`wiki/log.md`
- 收尾运行 `python tools/ingest.py --validate-only` 和 `python tools/build_graph.py`

## 健康检查工作流

- `/wiki-lint`
- 先运行 `python tools/lint.py`
- 结构性问题直接修复：断裂链接、缺失页面、frontmatter 不完整、孤立页面
- 语义问题只报告：矛盾、过时摘要、数据缺口
- 可询问是否保存到 `wiki/lint-report.md`
- 收尾运行 `python tools/ingest.py --validate-only`，并追加 `lint` 日志

## 图谱工作流

- `/wiki-graph`
- 先运行 `python tools/build_graph.py`
- 如需补充语义推断边，写回 `graph/graph.json` 后再次运行 `python tools/build_graph.py`
- 输出 `graph/graph.json` 和 `graph/graph.html`

## 刷新工作流

- `/wiki-refresh [--force]`
- 过期检测以 `python tools/check_stale.py` 为准；`python tools/refresh.py` 仅用于列出候选
- 对 `updated` / `new` 重新走导入工作流
- 对 `deleted` 询问是否删除对应来源页和索引条目
- 刷新完成后运行 `python tools/check_stale.py --update`
- 追加 `refresh` 日志

## 设置与切换

- `/wiki-setup` 负责安装全局 skills、注册知识库、创建新知识库
- `wiki-switch` 负责 `current`、`list`、`show`、`new`、`switch`
- `wiki-query`、`wiki-update`、`wiki-switch` 默认都按 `.env` 优先后的配置路径工作

## 命名规范

- 源页面 slug 必须严格匹配原始文件主名的 kebab-case；禁止按标题意译或重命名
- 实体页面使用 `TitleCase.md`
- 概念页面使用 `TitleCase.md`
- 页面内的 wikilink 不带目录前缀

## 日志格式

每条记录以 `## [YYYY-MM-DD] <操作> | <标题>` 开头。

操作类型：`ingest`、`ingest-all`、`query`、`update`、`lint`、`graph`、`refresh`
