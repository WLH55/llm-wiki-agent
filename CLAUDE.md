# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指导。

## 项目概述

LLM Wiki Agent 是一个知识管理工具。将源文档放入 `raw/` 目录，代理会读取、提取知识，并构建一个持久互联的知识库。每个新来源都让知识库更加丰富。所有知识库内容以纯 Markdown 文件形式存储——无数据库、无服务器。

## 常用命令

### Python 工具脚本（独立运行，需要 ANTHROPIC_API_KEY）

```bash
# 导入源文档到知识库
python tools/ingest.py raw/articles/my-article.md

# 查询知识库
python tools/query.py "主要主题有哪些？"

# 健康检查
python tools/lint.py
python tools/lint.py --save              # 保存报告到 wiki/lint-report.md

# 构建知识图谱
python tools/build_graph.py               # 完整重建
python tools/build_graph.py --no-infer    # 跳过语义推断（更快）
python tools/build_graph.py --open        # 构建后在浏览器中打开

# 修复缺失的实体页面
python tools/heal.py

# 刷新过期的源页面（重新导入已变更的文档）
python tools/refresh.py                   # 仅刷新已变更的来源
python tools/refresh.py --force           # 强制重新导入所有来源

# 将 PDF/arXiv 转换为 Markdown
python tools/pdf2md.py 2401.12345                           # arXiv ID
python tools/pdf2md.py paper.pdf --backend marker            # 本地 PDF
python tools/pdf2md.py paper.pdf -o raw/papers/output.md     # 自定义输出

# 批量转换目录中所有非 md 文件
python tools/file_to_markdown.py <输入目录>
```

### Claude Code 斜杠命令

| 命令 | 用途 |
|---|---|
| `/wiki-ingest <路径>` | 导入源文档（无需 API 密钥） |
| `/wiki-query <问题>` | 查询知识库并综合回答 |
| `/wiki-lint` | 健康检查：孤立页面、断开链接、矛盾 |
| `/wiki-graph` | 从 wikilink 构建知识图谱 |
| `/wiki-refresh` | 刷新过期来源页面（基于 SHA-256 哈希对比） |

### 依赖安装

```bash
pip install -e .                # 核心依赖，单一真源为 pyproject.toml
pip install arxiv2markdown      # arXiv PDF 转换
pip install marker-pdf          # 复杂学术 PDF（可选）
pip install pymupdf4llm         # 轻量 PDF 提取（可选）
```

要求 Python >=3.10, <3.14。

---

## 斜杠命令（Claude Code）

| 命令 | 用法 |
|---|---|
| `/wiki-ingest` | `ingest raw/my-article.md` |
| `/wiki-query` | `query: 主要主题有哪些？` |
| `/wiki-lint` | `lint the wiki` |
| `/wiki-graph` | `build the knowledge graph` |
| `/wiki-refresh` | `refresh` 或 `refresh --force` |

或者直接用自然语言描述：
- *"导入这个文件：raw/papers/attention-is-all-you-need.md"*
- *"知识库中关于 transformer 模型的内容是什么？"*
- *"检查知识库中的孤立页面和矛盾"*
- *"构建图谱并告诉我与 RAG 相关的内容"*

Claude Code 自动读取本文件并遵循以下工作流。

---

## 导入工作流

触发方式：*"ingest <文件>"* 或 `/wiki-ingest`

### 页面元数据规则

- `wiki/index.md` 和 `wiki/log.md` 是系统页面，不使用标准 frontmatter。
- 其他所有 wiki 页面都必须以 YAML frontmatter 开头。
- 每个普通 wiki 页面至少必须包含 `title`、`type` 和与页面类型对应的必需元数据字段。

步骤（按顺序）：
1. 使用 Read 工具完整读取源文档
2. 读取 `wiki/index.md` 和 `wiki/overview.md` 获取当前知识库上下文
3. 写入 `wiki/sources/<slug>.md` — 使用下面的源页面格式
4. 更新 `wiki/index.md` — 在 Sources 部分添加条目
5. 更新 `wiki/overview.md` — 如有必要则修订综合内容
6. 更新/创建提到的关键人物、公司、项目的实体页面
7. 更新/创建讨论的关键想法和框架的概念页面
8. 标记与现有知识库内容的任何矛盾
9. 追加到 `wiki/log.md`：`## [YYYY-MM-DD] ingest | <标题>`
10. **导入后验证** — 检查断裂的 `[[wikilinks]]`，验证所有新页面都在 `index.md` 中，打印变更摘要

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
2-4 句话概述。

## 核心论点
- 论点 1
- 论点 2

## 重要引述
> "引述内容" — 背景

## 关联
- [[EntityName]] — 关系说明
- [[ConceptName]] — 连接说明

## 矛盾
- 与 [[OtherPage]] 在以下方面矛盾：...
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
- [[OtherPage]] — 关系说明
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
- [[OtherPage]] — 关系说明
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

### 领域专用模板

如果来源属于特定领域（如个人日记、会议记录），代理应使用专用模板替代上面的通用模板：

#### 日记/日志模板
```markdown
---
title: "YYYY-MM-DD 日记"
type: source
tags: [diary]
date: YYYY-MM-DD
---
## 事件摘要
...
## 关键决定
...
## 精力与情绪
...
## 关联
...
## 变化与矛盾
...
```

#### 会议记录模板
```markdown
---
title: "会议名称"
type: source
tags: [meeting]
date: YYYY-MM-DD
---
## 目标
...
## 关键讨论
...
## 做出的决定
...
## 行动项
...
```

---

## 查询工作流

触发方式：*"query: <问题>"* 或 `/wiki-query`

步骤：
1. 读取 `wiki/index.md` 识别相关页面
2. 使用 Read 工具读取这些页面
3. 对于命中的源页面（`wiki/sources/`），从其 frontmatter 的 `source_file` 字段找到 `raw/` 中的原始文档，将原始内容也加入上下文
4. 综合 answered，内联引用使用 `[[PageName]]` wikilink 格式
5. 询问用户是否要将答案保存为 `wiki/syntheses/<slug>.md`

---

## 健康检查工作流

触发方式：*"lint the wiki"* 或 `/wiki-lint`

使用 Grep 和 Read 工具检查：
- **孤立页面** — 没有来自其他页面入站 `[[links]]` 的知识库页面
- **断裂链接** — 指向不存在页面的 `[[WikiLinks]]`
- **缺失或不完整的 frontmatter** — 普通 wiki 页面缺少 YAML frontmatter，或缺少其 `type` 对应的必需字段
- **矛盾** — 页面间冲突的论点
- **过时摘要** — 在更新来源后未更新的页面
- **缺失实体页面** — 在 3+ 页面中提到但没有专属页面的实体
- **数据缺口** — 知识库无法回答的问题；建议新来源

输出健康检查报告，询问用户是否保存到 `wiki/lint-report.md`。

---

## 图谱工作流

触发方式：*"build the knowledge graph"* 或 `/wiki-graph`

当用户要求构建图谱时，运行 `tools/build_graph.py`：
- 第一遍：解析所有 `[[wikilinks]]` → 确定性的 `EXTRACTED` 边
- 第二遍：推断隐式关系 → 带置信度分数的 `INFERRED` 边
- 运行 Louvain 社区检测
- 输出 `graph/graph.json` + `graph/graph.html`

如果用户没有安装 Python/依赖，改为手动生成图谱数据：
1. 使用 Grep 查找所有知识库页面中的 `[[wikilinks]]`
2. 构建节点/边列表
3. 直接写入 `graph/graph.json`
4. 使用 vis.js 模板写入 `graph/graph.html`

---

## 刷新工作流

触发方式：*"refresh"* 或 `/wiki-refresh`

当用户要求刷新过期来源时：
1. 运行 `python tools/check_stale.py` 检测变更（基于 SHA-256 哈希对比 `graph/.refresh_cache.json`）
2. 如果无过期来源，告知用户并结束
3. 对每个过期来源，重新执行导入工作流（同 /wiki-ingest 的步骤 3-9）
4. 刷新完成后运行 `python tools/check_stale.py --update` 更新哈希缓存
5. 输出摘要：刷新了几个、跳过了几个

追加到 `wiki/log.md`：`## [YYYY-MM-DD] refresh | 刷新了 N 个过期来源页面`

---

## 命名规范

- 源文档 slug：`kebab-case`，与源文件名匹配
- 实体页面：`TitleCase.md`（如 `OpenAI.md`、`SamAltman.md`）
- 概念页面：`TitleCase.md`（如 `ReinforcementLearning.md`、`RAG.md`）
- 源页面：`kebab-case.md`

## 索引格式

```markdown
# Wiki 索引

## 概览
- [概览](overview.md) — 动态综合

## 来源
- [源文档标题](sources/slug.md) — 一句话摘要

## 实体
- [实体名称](entities/EntityName.md) — 一句话描述

## 概念
- [概念名称](concepts/ConceptName.md) — 一句话描述

## 综合
- [分析标题](syntheses/slug.md) — 回答的问题
```

## 日志格式

每条记录以 `## [YYYY-MM-DD] <操作> | <标题>` 开头，便于 grep 解析：

```
grep "^## \[" wiki/log.md | tail -10
```

操作类型：`ingest`、`query`、`lint`、`graph`、`refresh`
