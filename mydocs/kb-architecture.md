# WeKnora 知识库（KB）架构文档

> 本文档系统整理 WeKnora 项目中"知识库"这一核心抽象的设计：KB 的类型、索引能力、文档与 FAQ 两种 RAG 子模式、Wiki 独立检索路径，以及它们之间的关系与边界。
>
> 适用对象：想要理解"知识库到底有几种""RAG 和 Wiki 怎么共存""FAQ 和文档为什么分开"等问题的开发者。
>
> Wiki 子系统的深入细节（存储、批处理、图片链路等）请参阅 [wiki-architecture.md](./wiki-architecture.md)，本文不重复。

---

## 目录

- [1. 一句话心智模型](#1-一句话心智模型)
- [2. 核心概念](#2-核心概念)
- [3. 知识库"有几种"——表面 vs 实际](#3-知识库有几种表面-vs-实际)
- [4. 两条独立检索路径](#4-两条独立检索路径)
- [5. RAG 的两个子模式：Document vs FAQ](#5-rag-的两个子模式document-vs-faq)
- [6. Wiki 文档不会再被分块](#6-wiki-文档不会再被分块)
- [7. 代码中"看似存在但未启用"的点](#7-代码中看似存在但未启用的点)
- [8. 一张图看清全貌](#8-一张图看清全貌)
- [9. 常见误解澄清](#9-常见误解澄清)
- [10. 关键文件索引](#10-关键文件索引)

---

## 1. 一句话心智模型

> **一个 KB 是一个组织容器。容器里能跑几条索引管线，由 4 个独立的布尔开关（`IndexingStrategy`）决定，而不是由"KB 类型"决定。**

用户在 UI 上看到的"文档库 / FAQ 库 / Wiki 库"是**前端投影**；后端真正决定行为的是 `IndexingStrategy` 的 4 个开关 + 一个仅用于"FAQ vs 非 FAQ"区分的 `Type` 字段。

---

## 2. 核心概念

### 2.1 KnowledgeBase（KB，知识库）

- **定义**：组织容器，是用户创建、共享、绑定到 Agent 的原子单元。
- **作用域**：多租户隔离（`tenant_id`）。
- **承载内容**：源文件（`knowledge`）、派生分块（`chunks`）、可选 wiki 页面（`wiki_pages`）、可选图谱实体（`graph_entities/relations`）。
- **代码位置**：`internal/types/knowledgebase.go`。

### 2.2 IndexingStrategy（索引策略，**真正的行为开关**）

4 个**完全独立**的布尔开关，**不是互斥的类型**：

| 开关 | 启用后行为 | 判定方法 |
|---|---|---|
| `VectorEnabled`   | 走 embedding 管线，写入向量库，支持向量召回 | `kb.IsVectorEnabled()` |
| `KeywordEnabled`  | 走 BM25/关键词索引，支持关键词召回         | `kb.IsKeywordEnabled()` |
| `WikiEnabled`     | 走 wiki 摄入管线，LLM 生成 wiki page        | `kb.IsWikiEnabled()` |
| `GraphEnabled`    | 走知识图谱抽取，写入实体/关系               | `kb.IsGraphEnabled()` |

- **代码位置**：`internal/types/indexing_strategy.go`。
- **`EnsureDefaults()`**：读取时会补默认值，避免老数据 nil panic。

### 2.3 Type（**遗留枚举，不要用它解释 KB 行为**）

`knowledge_bases.type` 列存的字符串：

| 取值 | 服务层是否读取 | 说明 |
|---|---|---|
| `document` | 是 | 区分走"文档 RAG 子模式"的元数据 + 摄入入口 |
| `faq`     | 是 | 区分走"FAQ RAG 子模式"的元数据 + 摄入入口 |
| `wiki`    | **否** | **保留但未使用** —— wiki 行为由 `IndexingStrategy.WikiEnabled` 控制 |

> **关键事实**：`KnowledgeBaseTypeWiki = "wiki"` 这个常量在服务层完全未被读取。即便 `type=wiki`，也只是名字叫 wiki；真正让一个 KB "能跑 wiki" 的，是 `IndexingStrategy.WikiEnabled = true`。

### 2.4 KBCapabilities（前端能力投影）

- **定义**：把 `IndexingStrategy + Type` 投影成前端可消费的 `{vector, keyword, wiki, graph, faq}` 5 元布尔对象。
- **作用**：让 UI 渲染"这个 KB 当前开了哪些能力"，不暴露内部 4 标志 + Type 的耦合细节。
- **代码位置**：`internal/types/knowledgebase.go` 中的 `KBCapabilities` 方法。

---

## 3. 知识库"有几种"——表面 vs 实际

### 3.1 用户视角（表面）

UI 让用户选的"KB 类型"通常是 3 种：

1. 文档知识库（Document KB）
2. FAQ 知识库（FAQ KB）
3. Wiki 知识库（Wiki KB）

### 3.2 代码视角（实际）

| "类型"        | 实际驱动因素 |
|---|---|
| 文档 KB       | `Type=document` + `IndexingStrategy.VectorEnabled/KeywordEnabled/GraphEnabled/WikiEnabled` 任意组合 |
| FAQ KB        | `Type=faq`    + `IndexingStrategy.VectorEnabled=true`（其他开关对 FAQ 无意义） |
| Wiki KB       | `IndexingStrategy.WikiEnabled=true`（`Type` 字段**不重要**，可 document 也可 wiki，行为一致） |

### 3.3 为什么 UI 分 3 种但代码只认 2 种 `Type`

- 文档 vs FAQ 是**真正的二分**：源数据形态（任意文件 vs 结构化 QA）、摄入管线、检索分区、chunk 元数据全部不同，必须用 `Type` 区分。
- Wiki 是**正交的能力**，不是互斥的类型：文档 KB 完全可以同时启用 wiki（先 RAG 切分，再 LLM 生成 wiki page）。所以 wiki 用开关而不是类型表达。

---

## 4. 两条独立检索路径

```
                       ┌─────────────────────────────┐
                       │      Agent 工具决策          │
                       └──────────────┬──────────────┘
                                      │
                ┌─────────────────────┼─────────────────────┐
                ▼                     ▼                     ▼
        ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
        │ knowledge_   │      │ wiki_search  │      │ graph_search │
        │   search     │      │ wiki_read_*  │      │  (可选)      │
        └──────┬───────┘      └──────┬───────┘      └──────────────┘
               │                     │
       ┌───────┴────────┐            │
       ▼                ▼            ▼
   ┌─────────┐    ┌─────────┐   ┌─────────────┐
   │ 向量召回 │    │关键词召回│   │ PG 全文+三元组│
   │+ rerank │    │  BM25   │   │ wiki_pages  │
   └────┬────┘    └────┬────┘   └─────────────┘
        │              │
        ▼              ▼
   ┌──────────────────────────┐
   │     chunks 表（共用）     │
   └──────────────────────────┘
```

### 4.1 RAG 检索路径

- **数据源**：`chunks` 表 + 向量库。
- **触发条件**：`VectorEnabled` 和/或 `KeywordEnabled` 为真。
- **Agent 工具**：`knowledge_search`（详见 `internal/agent/tools/`）。
- **支持来源**：Document KB（任意文档分块）和 FAQ KB（`chunk_type=faq`），共享同一张 `chunks` 表，但在向量库中走**不同分区**（详见第 5 节）。

### 4.2 Wiki 检索路径

- **数据源**：`wiki_pages` 表（独立于 `chunks`）。
- **触发条件**：`WikiEnabled = true`。
- **Agent 工具**：`wiki_search`、`wiki_read_page`、`wiki_read_source_doc`。
- **检索实现**：PostgreSQL `to_tsvector` GIN 全文索引 + `pg_trgm` 三元组相似度。
- **细节深挖**：见 [wiki-architecture.md 第 7 节](./wiki-architecture.md#7-wiki-与向量数据的关系)。

### 4.3 两条路径的关系

- **基本完全独立**：不同的表、不同的索引、不同的 Agent 工具，故障域隔离。
- **共享 KB ID 命名空间**：同一个 KB 可以同时支持两条路径，Agent 可以对同一个 KB 同时调 `knowledge_search` 和 `wiki_search`。
- **数据互不流转**：wiki page 默认**不会**被向量化进 `chunks`（详见第 6 节）。

---

## 5. RAG 的两个子模式：Document vs FAQ

两者共享 RAG 底座（`chunks` 表、向量召回器），但在 5 个点上分化：

| 维度 | Document KB | FAQ KB |
|---|---|---|
| **源数据形态** | 任意文件（PDF/Word/Markdown/HTML/...） | 结构化 QA 集合 |
| **摄入入口** | 文件上传 → DocReader 解析 → 多模态分块 | 前端解析 QA 文件 → 后端 batch API |
| **支持的文件类型** | 任意（通过 `accept` 控制） | **仅 `.json` / `.csv` / `.xlsx` / `.xls`**（前端 `FAQEntryManager.vue` 强制） |
| **chunk 元数据** | `DocumentChunkMetadata`（页码、坐标、bbox 等） | `FAQChunkMetadata`：`StandardQuestion`、`SimilarQuestions`、`NegativeQuestions`、`Answers`、`AnswerStrategy` |
| **chunk 类型**     | `text` / `parent_text` / `image_ocr` / `image_caption` / `summary` / `entity` / `relationship` / `table_summary` / `table_column` / `web_search` | `faq` |
| **检索路由** | 向量 + 关键词（`docVectorKBIDs` + `docKeywordKBIDs`） | **仅向量**（`faqVectorKBIDs`，FAQ KB 被显式排除在关键词索引外，见 `knowledgebase_search.go`） |
| **索引参数** | 无特殊配置 | `FAQConfig.IndexMode`（`question_only` / `question_answer`）、`QuestionIndexMode`（`combined` / `separate`） |
| **独有概念** | 无 | "反例问题"（`NegativeQuestions`）—— 仅对 QA 匹配有意义 |

### 5.1 FAQ 的上传机制（重要澄清）

> **澄清**：FAQ KB **支持文件上传**，但只接受**结构化 QA 格式**（`.json` / `.csv` / `.xlsx` / `.xls`）。
>
> **不要**理解为"FAQ 不能上传文件"。准确说法是"FAQ 不接受任意非结构化文档"。

工作流程：

```
用户在 FAQ 设置界面选择 .json / .csv / .xlsx / .xls 文件
        │
        ▼  （frontend/src/views/knowledge/components/FAQEntryManager.vue）
   前端解析文件
   ├─ .json   → JSON.parse
   ├─ .csv    → papaparse（自动处理引号、转义、分隔符）
   └─ .xlsx   → XLSX.utils.sheet_to_json
        │
        ▼
   FAQEntryPayload[]（标准问 + 相似问 + 反例 + 答案 + 策略）
        │
        ▼  HTTP POST
   后端 batch upsert API（internal/application/service/knowledge_faq_import.go）
        │
        ▼
   异步任务（asynq）：
   1. dry run 校验（格式 / 批内重复 / 库内重复 / 内容安全）
   2. 实际写入 chunks（chunk_type=faq，挂 FAQChunkMetadata）
   3. 向量化（按 IndexMode 决定 embed 的是问题还是问题+答案）
   4. 进度回写到 Redis
```

后端**没有** FAQ 文件解析端点——文件解析完全发生在前端，后端只接收已结构化的 `FAQEntryPayload[]`。这是有意为之：让格式校验、预览、dry run 在浏览器里完成，降低后端负担并提供即时反馈。

### 5.2 为什么 Document / FAQ 不合并成一个 Type

虽然共享 RAG 底座，但分化点太多：

1. **摄入语义不同**：文档是"长文本 → 切片"，FAQ 是"离散 QA → 一个 QA 一个 chunk"。
2. **元数据形状不同**：强行合并要么让 `DocumentChunkMetadata` 塞一堆可空字段，要么让 `FAQChunkMetadata` 失去强类型。
3. **检索分区不同**：FAQ 必须独立向量分区（避免问"产品规格"时召回 FAQ 的退货政策），且不参与关键词索引（QA 太短，BM25 效果差）。
4. **配置项不同**：FAQ 需要索引模式（仅问题 / 问题+答案）、反例问题、答案策略；文档则不需要。
5. **概念独占**：FAQ 的"反例问题"在文档场景无对应物。

所以保留两个 Type 是为了**让两种业务场景的代码路径清晰分离**，同时共享底层 RAG 基础设施。

---

## 6. Wiki 文档不会再被分块

这是一个**容易误解**的点，单独说明：

### 6.1 完整链路

```
用户上传 PDF
    │
    ▼ DocReader 解析
markdown
    │
    ├──→ chunks 表（chunk_type=text/image_ocr/...）   ← RAG 检索源
    │
    └──→ Wiki 摄入管线（30s 去抖动 + Map-Reduce）
            │
            │  LLM 抽实体/概念/摘要，生成 markdown 页面
            │  含 [[slug|display]] 双向链接、图片 URL、章节结构
            ▼
        wiki_pages 表（独立表）
            │
            │  ❌ 不再二次分块
            ▼
        PG to_tsvector GIN 索引（独立检索路径）
```

### 6.2 为什么 wiki page 不进 chunks 表

| 原因 | 说明 |
|---|---|
| **语义已组织** | wiki page 是 LLM 综合产物，已自带章节/链接/摘要，进一步切片会破坏语义边界 |
| **检索模型不同** | wiki 用 PG 全文 + 三元组（结构化查询），RAG 用向量相似度（模糊召回），两者各有适用场景 |
| **避免双倍存储** | 同一段信息既存 wiki page 又存 chunk 是冗余；且 wiki page 内容会随 LLM 重写变化，保持 chunks 同步代价高 |
| **故障域隔离** | wiki LLM 失败不应该污染向量检索结果；两套路径独立演进 |

### 6.3 例外：预留接口

代码里**预留**了 `ChunkTypeWikiPage = "wiki_page"` 常量（`internal/types/chunk.go`）和 `chat_pipeline/wiki_boost.go` 加权插件，但**没有任何代码把 wiki page 写入 chunks**。详见下一节。

---

## 7. 代码中"看似存在但未启用"的点

阅读源码时容易踩坑的几处"幽灵代码"——**保留但当前不工作**：

| 位置 | 名字 | 状态 |
|---|---|---|
| `internal/types/chunk.go` | `ChunkTypeWikiPage = "wiki_page"` | 常量定义存在，但**没有任何写入逻辑**会产出这种 chunk |
| `internal/types/knowledgebase.go` | `KnowledgeBaseTypeWiki = "wiki"` | 常量定义存在，但服务层**从不读取**（wiki 行为由 `IndexingStrategy.WikiEnabled` 决定） |
| `internal/application/service/wiki_page.go:926` | `deleteChunkForPage` | 删除 wiki page 时会清理 `wp-<pageID>` 前缀的 chunk，但**找不到对应的 `upsertChunkForPage`**（写入端缺失） |
| `internal/application/service/chat_pipeline/wiki_boost.go` | WikiBoost 插件 | 给 `ChunkTypeWikiPage` chunk 加 1.3× 权重，但因没人写入这种 chunk，**实际空跑** |

> **解读**：这些是设计上**预留的结合点**，为未来"wiki page 参与向量召回"留好了接口。当前实现选择让 wiki 和 RAG 完全分离。

---

## 8. 一张图看清全貌

```
┌──────────────────────────────────────────────────────────────────────┐
│                       KnowledgeBase（容器）                           │
│  ──────────────────────────────────────────────────────────────────  │
│  Type: document | faq          IndexingStrategy (4 个独立开关):      │
│  (wiki 已弃用，仅 document/     ├─ VectorEnabled                    │
│   faq 影响摄入路径)             ├─ KeywordEnabled                   │
│                                 ├─ WikiEnabled                      │
│                                 └─ GraphEnabled                     │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │             源文件层（knowledge 表）                         │    │
│  │   文档（PDF/Word/...）   ─┐                                  │    │
│  │   FAQ QA（json/csv/xlsx）─┘                                  │    │
│  └─────────────────────────────┬───────────────────────────────┘    │
│                                │                                     │
│       ┌────────────────────────┴────────────────────────┐           │
│       ▼                                                 ▼           │
│  ┌──────────────────┐                         ┌──────────────────┐  │
│  │  Document 摄入   │                         │   FAQ 摄入       │  │
│  │  DocReader 解析  │                         │  前端解析 QA 文件│  │
│  │  → 多模态分块    │                         │  → batch API     │  │
│  └────────┬─────────┘                         └────────┬─────────┘  │
│           │                                            │            │
│           ▼                                            ▼            │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              chunks 表（chunk_type: text/parent_text/        │   │
│  │              image_ocr/image_caption/summary/entity/         │   │
│  │              relationship/faq/web_search/...）               │   │
│  │                                                              │   │
│  │   Document chunks                  FAQ chunks                │   │
│  │   (docVectorKBIDs, docKeywordKBIDs) (faqVectorKBIDs,         │   │
│  │                                     无关键词索引)            │   │
│  └─────────────────────────────┬───────────────────────────────┘   │
│                                │                                     │
│                                ▼                                     │
│                  向量库 + BM25 索引                                  │
│                                                                       │
│  ════════════════════════  Wiki 路径（独立）  ════════════════════   │
│                                                                       │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │  Wiki 摄入（仅当 WikiEnabled=true）                       │       │
│  │  30s 去抖动 → Map-Reduce（LLM 抽实体/概念/摘要）          │       │
│  └────────────────────────────┬─────────────────────────────┘       │
│                               ▼                                       │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │  wiki_pages 表（独立于 chunks，不再分块）                 │       │
│  │  PG to_tsvector GIN + pg_trgm 三元组                      │       │
│  └──────────────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────┘

                          ↑ Agent 检索时 ↑
              ┌───────────┴───────────────────┐
              │                               │
      knowledge_search                  wiki_search / wiki_read_*
       （RAG 路径）                       （Wiki 路径）
```

---

## 9. 常见误解澄清

| 误解 | 事实 |
|---|---|
| "Wiki 是一种独立的 KB 类型" | wiki 行为由 `IndexingStrategy.WikiEnabled` 控制，`Type=wiki` 是保留但未读取的值 |
| "FAQ 不能上传文件" | FAQ **可以**上传文件，但仅限 `.json/.csv/.xlsx/.xls` 等结构化 QA 格式 |
| "FAQ 和 Document 是两套独立检索系统" | 两者都是 RAG 路径的子模式，共享 `chunks` 表和向量召回器；区别仅在摄入、元数据、检索分区 |
| "wiki page 会被分块进 chunks 表参与向量召回" | wiki page 不再分块，写入独立的 `wiki_pages` 表，走 PG 全文索引；`ChunkTypeWikiPage` 是预留但未启用的常量 |
| "一个 KB 只能选一种索引方式" | 4 个 `IndexingStrategy` 开关可任意组合（如同时开 vector + keyword + wiki + graph） |
| "Document / FAQ / Wiki 是 3 个并列的概念" | Document 和 FAQ 是 RAG 路径下的二分（摄入语义不同）；Wiki 是与 RAG 并列的另一条独立路径 |

---

## 10. 关键文件索引

### 类型与常量

| 文件 | 内容 |
|---|---|
| `internal/types/knowledgebase.go` | `KnowledgeBase` 结构、`IndexingStrategy` 投影方法（`IsVectorEnabled` 等）、`KBCapabilities`、`EnsureDefaults` |
| `internal/types/indexing_strategy.go` | `IndexingStrategy` 4 标志定义、`DefaultIndexingStrategy` |
| `internal/types/chunk.go` | 所有 `ChunkType*` 常量（含预留的 `ChunkTypeWikiPage`） |
| `internal/types/faq.go` | `FAQChunkMetadata`、`FAQEntry`、`FAQEntryPayload`、`FAQBatchUpsertPayload` |

### KB 主服务

| 文件 | 内容 |
|---|---|
| `internal/application/service/knowledge_create.go` | KB 创建逻辑（含 `Type` 与 `IndexingStrategy` 的初始组合校验） |
| `internal/application/service/knowledgebase_search.go` | 检索分区逻辑（`faqVectorKBIDs` / `docVectorKBIDs` / `docKeywordKBIDs`） |

### Document 摄入

| 文件 | 内容 |
|---|---|
| `internal/application/service/knowledge_process.go` | 文档摄入主流程（解析、分块、向量化、图谱、wiki 触发） |
| `internal/infrastructure/docparser/` | DocReader 解析器、图片抽取 |

### FAQ 摄入

| 文件 | 内容 |
|---|---|
| `internal/application/service/knowledge_faq_import.go` | `UpsertFAQEntries`、`ProcessFAQImport`（asynq）、dry run 校验、增量更新、CSV 导出 |
| `internal/handler/faq.go` | FAQ HTTP handler（batch upsert、export CSV 等） |
| `frontend/src/views/knowledge/components/FAQEntryManager.vue` | 前端文件解析（`.json/.csv/.xlsx`）、预览、提交 |

### Wiki 摄入（详见 [wiki-architecture.md](./wiki-architecture.md)）

| 文件 | 内容 |
|---|---|
| `internal/application/service/wiki_ingest*.go` | Wiki 摄入管线（去抖动、Map-Reduce、Dedup） |
| `internal/application/service/wiki_page.go` | `WikiPageService`（CRUD、链接维护、`deleteChunkForPage`） |
| `internal/application/service/chat_pipeline/wiki_boost.go` | 预留但未启用的向量加权插件 |

### Agent 工具

| 文件 | 内容 |
|---|---|
| `internal/agent/tools/` | `knowledge_search`、`wiki_search`、`wiki_read_page`、`wiki_read_source_doc` 等工具定义 |
| `internal/agent/tools/capabilities.go` | 工具能力映射 |

### 数据库迁移

| 文件 | 内容 |
|---|---|
| `migrations/versioned/000037_*` | `indexing_strategy` 列、`wiki_config` 列、wiki 三张表 |
| `migrations/versioned/000040_*` | `wiki_log_entries` 表 |
| `migrations/versioned/000041_*` | `task_pending_ops` / `task_dead_letters` + wiki_pages GIN 索引 |
| `migrations/versioned/000061_*` | wiki_pages 层级字段 + wiki_folders 重定义 |

---

## 附录：与领域词汇表的对应

本文档与根目录 [CONTEXT.md](../CONTEXT.md) 的"领域语言"部分一一对应：
- `KnowledgeBase` / `IndexingStrategy` / `Capabilities` / `Type (legacy)` → 见本文第 2 节
- `Knowledge` / `Chunk` → 见本文第 5 节
- `RAG retrieval` / `Wiki retrieval` → 见本文第 4 节
- `Document KB` / `FAQ KB` → 见本文第 5 节

---

*本文档基于代码状态：2026-07-05 / commit `7d8a80ae`。Wiki 子系统细节请参阅 [wiki-architecture.md](./wiki-architecture.md)。*
