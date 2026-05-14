# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库中工作时提供指导。

## 项目概述

LLM Wiki Agent 是一个知识管理工具。将源文档放入 `raw/` 目录，代理会读取、提取知识，并构建一个持久互联的知识库。每个新来源都让知识库更加丰富。所有知识库内容以纯 Markdown 文件形式存储——无数据库、无服务器。

## 常用命令

### Python 工具脚本（机械执行，不调用 LLM）

```bash
# 验证 wiki 完整性（断链、未索引页面）
python tools/ingest.py --validate-only

# 查找与问题相关的 wiki 页面（关键词匹配）
python tools/query.py "主要主题有哪些？"

# 健康检查（结构 + 图感知，不含语义检查）
python tools/lint.py
python tools/lint.py --save              # 保存报告到 wiki/lint-report.md

# 构建知识图谱（提取 wikilink 边 + 保留已有推断边）
python tools/build_graph.py               # 构建图谱
python tools/build_graph.py --open        # 构建后在浏览器中打开
python tools/build_graph.py --report      # 生成图谱健康报告

# 检测过期的源页面（哈希对比，不执行刷新）
python tools/refresh.py                   # 列出过期来源
python tools/refresh.py --force           # 强制标记所有来源为过期

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
| `/wiki-ingest <路径>` | 导入源文档 |
| `/wiki-query <问题>` | 查询知识库并综合回答 |
| `/wiki-lint` | 健康检查：孤立页面、断开链接、矛盾 |
| `/wiki-graph` | 从 wikilink 构建知识图谱 |
| `/wiki-refresh` | 刷新过期来源页面（基于 SHA-256 哈希对比） |

### 依赖安装

```bash
pip install -e .                # 核心依赖，单一真源为 pyproject.toml
pip install networkx            # 社区检测（可选，build_graph.py --report 需要）
pip install arxiv2markdown      # arXiv PDF 转换
pip install marker-pdf          # 复杂学术 PDF（可选）
pip install pymupdf4llm         # 轻量 PDF 提取（可选）
```

要求 Python >=3.10, <3.14。工具脚本不依赖 litellm 或 API 密钥。

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
3. **防重检查与写入**：在写入 `wiki/sources/` 之前，必须使用 `grep` 工具在 `wiki/sources/` 目录下搜索 `source_file: <当前原始文件路径>` 是否已存在于其他源页面中。
   - 如果找到了现有的源页面（即使文件名不符合当前规范），必须**覆盖更新**该现有文件，或者将其删除并使用规范的 `<slug>.md` 重建。**绝对禁止为同一个原始文件创建两个源页面。**
   - 如果未找到，则正常写入 `wiki/sources/<slug>.md` — 使用下面的源页面格式
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
1. 读取 wiki/index.md 识别最相关的页面
2. 读取这些页面（最多约 10 个最相关的）
3. 综合生成一份详尽的 Markdown 答案，使用 [[页面名称]] 形式的 Wiki 链接进行引用；
4. 在答案末尾添加 ## 来源 部分，列出你所引用的所有页面；
5. 询问用户是否需要将此答案保存为 wiki/syntheses/<slug>.md 文件。
6. 如果用户同意，执行**合成页面保存子流程**（见下）

### 合成页面保存子流程

当用户确认保存 synthesis 页面时，按以下步骤执行：

1. **写入文件** — 将综合答案保存为 `wiki/syntheses/<slug>.md`，slug 规则同源页面（kebab-case）
2. **更新 index.md** — 在 `## 综合` 部分添加条目
3. **补充缺失的实体/概念页面** — 扫描答案中的 `[[wikilinks]]`，对于指向不存在页面的链接：
   - 在 `wiki/entities/` 或 `wiki/concepts/` 创建对应页面（一句话定义 + 关联回 synthesis）
   - 更新 `index.md` 的对应部分
4. **更新已有实体/概念页面** — 对于答案中引用的已存在页面，在 `## 关联` 中补充指向本 synthesis 的链接（如果尚无）
5. **更新 overview.md** — 如果 synthesis 内容改变了项目的整体理解，修订 overview
6. **追加日志** — 在 `wiki/log.md` 添加 `## [YYYY-MM-DD] query | <综合标题>`
7. **运行 `python tools/build_graph.py`** — 重建知识图谱，使新页面和边生效
8. **验证** — 运行 `python tools/ingest.py --validate-only` 检查断链和未索引页面
9. **输出摘要** — 告知用户新建/更新了哪些页面、图谱已重建

---

## 健康检查工作流

触发方式：*"lint the wiki"* 或 `/wiki-lint`

### 第一阶段：检测

1. 运行 `python tools/lint.py` 获取结构性问题
2. Claude 语义检查：矛盾、过时内容、数据缺口

### 第二阶段：自动修复

对以下问题**直接修复，无需确认**：

- **断裂链接与缺失页面** — `[[wikilink]]` 指向不存在的页面，直接创建目标页面（实体/概念页）
- **缺失或不完整的 frontmatter** — 补全 `title`、`type`、`sources`、`last_updated` 等必需字段
- **孤立页面** — 在相关页面的 `## 关联` 中添加指向孤立页面的 wikilink

### 第三阶段：输出待办

仅对**无法自动修复**的问题输出报告，需要人工判断：

- **矛盾** — 页面间冲突的论点，列出冲突位置供用户裁决
- **过时摘要** — 源文档已更新但 synthesis 未同步，提示需要重新查询
- **数据缺口** — 知识库无法回答的重要问题，建议具体的新来源

### 收尾

1. 追加到 `wiki/log.md`：`## [YYYY-MM-DD] lint | 自动修复 N 个问题，N 个待人工处理`
2. 运行 `python tools/ingest.py --validate-only` 确认修复后无残留问题
3. 输出摘要：修复了什么、还有哪些待办

---

## 图谱工作流

触发方式：*"build the knowledge graph"* 或 `/wiki-graph`

当用户要求构建图谱时：

1. 运行 `python tools/build_graph.py` 完成机械部分：
   - 从 wiki 页面构建节点
   - 解析所有 `[[wikilinks]]` → 确定性的 `EXTRACTED` 边
   - 保留 graph.json 中已有的 INFERRED/AMBIGUOUS 边
   - 运行 Louvain 社区检测
   - 输出 `graph/graph.json` + `graph/graph.html`
2. 读取 graph.json，Claude 对节点进行语义推断
3. 将推断边写入 graph.json，重新运行 `build_graph.py` 生成最终 HTML

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

- 源文档 slug：**必须**转换为小写英文 `kebab-case` 且**严格与源文件名的主名匹配**（例如 `raw/articles/My Article.md` 对应 `my-article.md`），**严禁根据文章标题或内容自行翻译或生造 slug。**
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
