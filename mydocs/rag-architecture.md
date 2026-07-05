# WeKnora RAG 架构文档

> 本文档系统整理 WeKnora 中"RAG（Retrieval-Augmented Generation）路径"的端到端设计：一份文件从被上传，到被切片、向量化、存储、检索、融合、（可选）重排，最终把上下文交回给 LLM 的全过程。
>
> 适用对象：想要理解"RAG 管线分几步""父子分块到底怎么用""向量与 BM25 怎么融合""多源召回如何去重"等问题的开发者。
>
> 配套阅读：
> - [kb-architecture.md](./kb-architecture.md) —— KB 容器与 IndexingStrategy 的语义（本文不重复）
> - [wiki-architecture.md](./wiki-architecture.md) —— Wiki 独立检索路径（本文不展开）

---

## 目录

- [1. 一句话心智模型](#1-一句话心智模型)
- [2. 端到端全景图](#2-端到端全景图)
- [3. 摄取：分阶段流水线](#3-摄取分阶段流水线)
- [4. 存储：chunks 是真相，向量库/BM25 是索引副本](#4-存储chunks-是真相向量库bm25-是索引副本)
- [5. 检索：分区、归一化、RRF 融合、（可选）Rerank](#5-检索分区归一化-rrf-融合可选rerank)
- [6. 数据表清单](#6-数据表清单)
- [7. 常见误解澄清](#7-常见误解澄清)
- [8. 关键文件索引](#8-关键文件索引)

---

## 1. 一句话心智模型

> **WeKnora 的 RAG 是一条"5 串行 + 4 并行"的摄入流水线，加上一套"分区召回 → 分数归一化 → RRF 融合 → 可选 rerank"的检索流水线。底层用 `chunks` 表作为单一事实来源，向量库和 BM25 索引只是 `chunks` 的派生副本。**

抽象层级：

```
 ingestion（写入）                storage（持久化）              retrieval（读取）
 ────────────────                 ────────────────              ────────────────
 DocReader                        chunks 表（真相）              三向分区
   ↓                                ↓                            （faq / doc-vector / doc-keyword）
 Chunking                        ┌─────────────────┐             ↓
   ↓                             │  向量库（派生）  │           向量召回 + 关键词召回
 Embedding                       │  + BM25 索引    │             ↓
   ↓                             └─────────────────┘           分数归一化（仅向量）
 Multimodal                                                      ↓
   ↓                                                            RRF 融合
 PostProcess                                                     ↓
   ↓                                                            （chat_pipeline 内）
 └─→ 4 个并行扇出：                                              Rerank 插件
     Summary / Question-Gen / Wiki-Ingest / Graph-Extract         ↓
                                                                返回上下文给 LLM
```

---

## 2. 端到端全景图

```
       ┌─────────────────────────── ingestion ───────────────────────────┐

       DocReader ─→ Chunking ─→ Embedding ─→ Multimodal ─→ PostProcess
          │           │            │             │              │
          │           │            │             │              ├─→ Summary（并行）
          │           │            │             │              ├─→ Question Generation（并行）
          │           │            │             │              ├─→ Wiki Ingest（并行，仅 WikiEnabled）
          │           │            │             │              └─→ Graph Extract（并行，仅 GraphEnabled）
          │           │            │             │
          └───────────┴────────────┴─────────────┴── all settled ──→ Knowledge.status = completed

       ┌─────────────────────────── storage ─────────────────────────────┐

       ┌───────────────┐        派生           ┌──────────────────┐
       │  chunks 表    │ ───────────────────→  │   向量库（多引擎）│
       │  （真相）     │ ───────────────────→  │   BM25 索引      │
       └───────────────┘                       └──────────────────┘

       ┌─────────────────────────── retrieval ───────────────────────────┐

       ┌──── faqVectorKBIDs ────────────┐
       │                                │
       │  FAQ KB（仅向量，无关键词）    │
       └────────────────────────────────┘

       ┌──── docVectorKBIDs ─┐  ┌──── docKeywordKBIDs ─┐
       │                     │  │                      │
       │  Document KB 向量   │  │  Document KB 关键词  │
       └─────────────────────┘  └──────────────────────┘
                   │                       │
                   ↓                       ↓
              归一化到 [0,1]            未经归一化（原样）
                   │                       │
                   └───────────┬───────────┘
                               ↓
                          RRF 融合
                               ↓
                       （chat_pipeline 内）
                       Rerank 插件（可选）
                               ↓
                       top-k 返回给 LLM
```

---

## 3. 摄取：分阶段流水线

主入口：[`internal/application/service/knowledge_process.go`](../internal/application/service/knowledge_process.go)。

### 3.1 5 个串行阶段（前段）

| 阶段 | 入口行号 | 作用 |
|---|---|---|
| `StageDocReader`   | `knowledge_process.go:3099` | 把上传的原始文件（PDF/Word/HTML/Markdown/...）解析为 markdown + 抽取图片 |
| `StageChunking`    | `knowledge_process.go:488`  | 切分父子分块、扁平分块；写 `chunks` 表（父子分块**进数据库但不进向量库**） |
| `StageEmbedding`   | `knowledge_process.go:520`  | 仅为子/扁平分块生成文本向量；写向量库 |
| `StageMultimodal`  | `knowledge_process.go:657`  | 图片 OCR、图片 caption，按需生成多模态向量 |
| `StagePostProcess` | `post_process.go:92`        | 触发 4 个并行扇出（详见 3.3） |

> **为什么串行**：每一阶段的输入都依赖上一阶段的产物（DocReader 出 markdown，Chunking 才能切；切完才能 embed；embed 完才能做多模态；多模态结束才能触发后置任务）。强制串行让阶段树清晰、失败可重试到具体阶段。

### 3.2 父子分块（small-to-large retrieval）

**核心思想**：用小块做召回（向量相似度更精准），用大块做上下文（给 LLM 更完整的语义）。

```
原文档 markdown
    │
    ↓  Chunking 阶段
父分块（较大，~1024 token 量级）
    │
    ├──→ 写入 chunks 表（chunk_type=parent_text）
    │    【**不**进向量库】
    │
    └──→ 进一步切分为
         子分块（较小，~256 token 量级）
              │
              ├──→ 写入 chunks 表（chunk_type=text）
              │    字段 parent_chunk_id 指向父
              │
              └──→ 进向量库（被 embed，参与召回）
```

代码证据：

- [`knowledge_process.go:413`](../internal/application/service/knowledge_process.go#L413) 注释：「优先添加父分块（它们会进入数据库，但不会进入向量索引）」
- [`knowledge_process.go:521-522`](../internal/application/service/knowledge_process.go#L521) 注释：「仅为子/扁平分块创建索引信息，而非父分块。父分块是为上下文检索而存储的」
- [`knowledge_process.go:441-443`](../internal/application/service/knowledge_process.go#L441) 每个子分块都写 `parent_chunk_id` 字段

**召回时的行为**：向量库返回的是子分块的 chunk_id；服务层拿着 chunk_id 去 `chunks` 表查 `parent_chunk_id`，把**父分块**作为上下文返回给 LLM。LLM 看到的是更完整的语义窗口，而不是被切碎的小片段。

> **例外**：当 `IndexingStrategy` 决定不切父子（小块本身就够大），就只产出 `chunk_type=text` 的"扁平分块"——既进向量库，也直接作为上下文。

### 3.3 4 个并行扇出（后段）

`StagePostProcess` 之后，4 个相互独立的子任务**并行扇出**：

| 扇出 | 触发条件 | 产物 |
|---|---|---|
| **Summary**            | 始终                       | 为每个父分块生成摘要 chunk（`chunk_type=summary`），同样进向量库 |
| **Question Generation**| 始终                       | 为每个分块生成"可能的提问"，作为额外召回向量（增强 query 与文档的语义对齐） |
| **Wiki Ingest**        | `kb.IsWikiEnabled()`       | 触发 wiki 摄入管线（30s 去抖动 + Map-Reduce 生成 wiki page），详见 [wiki-architecture.md](./wiki-architecture.md) |
| **Graph Extract**      | `kb.IsGraphEnabled()`      | 抽取实体与关系，写入 `chunks` 表（`chunk_type=entity/relationship`） |

> **为什么并行**：4 个扇出相互独立，没有数据依赖。串行会让尾部时延累加（Summary + Question + Wiki + Graph 全跑完才能完成 Knowledge），并行后整体时延 ≈ max(各扇出时延)。

### 3.4 状态机与 Span 追踪

#### Knowledge 状态机

`knowledges.status` 列的状态流转（见 `migrations/versioned/000056_knowledge_pending_subtasks.up.sql`）：

```
pending → processing → finalizing → completed
              │
              └─→ failed（任一阶段失败）
```

- `pending`：刚创建，未开始
- `processing`：5 串行阶段中
- `finalizing`：4 并行扇出中（`pending_subtasks_count > 0`）
- `completed`：所有子任务完成（`pending_subtasks_count == 0`）

`pending_subtasks_count` 列记录未完成的并行子任务数；每完成一个子任务原子减一，减到 0 时整体进入 `completed`。

#### Span 追踪

`knowledge_processing_spans` 表（见 `migrations/versioned/000055_knowledge_processing_spans.up.sql`）模仿 Langfuse 词汇：

| span_type | 含义 |
|---|---|
| `root`       | 一次 Knowledge 处理的根 span（绑定 `knowledge_id` + `attempt`） |
| `stage`      | 5 个串行阶段之一 |
| `subspan`    | 阶段内的子操作（如 DocReader 解析单页） |
| `generation` | LLM 调用（如 Summary、Question Gen） |

每个 span 记录 `started_at / ended_at / status / error`，可通过 `parent_span_id` 组成树。**用途**：UI 上"摄入进度"的细粒度可视化、失败定位、性能分析。

---

## 4. 存储：chunks 是真相，向量库/BM25 是索引副本

### 4.1 chunks 表的字段结构

[`migrations/versioned/000000_init.up.sql:179`](../migrations/versioned/000000_init.up.sql#L179) 定义了 `chunks` 表的核心字段：

| 字段 | 类型 | 含义 |
|---|---|---|
| `id`                          | uuid        | 主键 |
| `knowledge_id`                | uuid        | 所属 Knowledge（外键到 `knowledges` 表） |
| `knowledge_base_id`           | uuid        | 所属 KB（外键到 `knowledge_bases` 表） |
| `chunk_type`                  | varchar     | 分块类型枚举（详见 4.2） |
| `content`                     | text        | 分块文本内容 |
| `parent_chunk_id`             | uuid        | **父分块 ID**（small-to-large retrieval 关键） |
| `relation_chunks`             | jsonb       | 直接相关 chunk IDs |
| `indirect_relation_chunks`    | jsonb       | 间接相关 chunk IDs（图谱扩展） |
| `metadata`                    | jsonb       | 类型相关的元数据（`DocumentChunkMetadata` / `FAQChunkMetadata`） |
| `vector_store_id`             | uuid        | 该 chunk 在向量库中的位置（多引擎场景） |
| `created_at / updated_at`     | timestamptz | 时间戳 |

> **关键点**：`parent_chunk_id` + `relation_chunks` + `indirect_relation_chunks` 让 `chunks` 表自身就承载了"图谱"结构。WeKnora **没有**独立的 `graph_entities` / `graph_relations` 表——它们以 `chunk_type=entity` / `chunk_type=relationship` 的形式**混在 chunks 表里**。

### 4.2 chunk_type 的 12 种取值

[`internal/types/chunk.go`](../internal/types/chunk.go) 定义：

| chunk_type        | 写入方                                  | 是否进向量库 | 说明 |
|---                |---                                      |:-:|---|
| `text`            | Chunking 阶段                           | ✅ | 子分块（或扁平分块），召回主入口 |
| `parent_text`     | Chunking 阶段                           | ❌ | 父分块，仅作为上下文 |
| `image_ocr`       | Multimodal 阶段                         | ✅ | 图片 OCR 文本 |
| `image_caption`   | Multimodal 阶段                         | ✅ | 图片 caption（LLM 生成） |
| `summary`         | Summary 扇出                            | ✅ | 父分块的摘要 |
| `entity`          | Graph Extract 扇出                      | ✅ | 抽取的实体（"图实体"实际是这种 chunk） |
| `relationship`    | Graph Extract 扇出                      | ✅ | 抽取的关系（"图关系"实际是这种 chunk） |
| `table_summary`   | Chunking / Multimodal                   | ✅ | 表格的语义摘要 |
| `table_column`    | Chunking / Multimodal                   | ✅ | 表格的列级切片 |
| `web_search`      | Agent 运行时                            | ✅ | Agent 抓取的网页内容 |
| `faq`             | FAQ 摄入                                | ✅ | FAQ QA 对（详见 [kb-architecture.md 第 5 节](./kb-architecture.md#5-rag-的两个子模式document-vs-faq)） |
| `wiki_page`       | **预留，无写入逻辑**                    | - | 见 [kb-architecture.md 第 7 节](./kb-architecture.md#7-代码中看似存在但未启用的点) |

### 4.3 多向量库抽象

WeKnora 不绑定向量库引擎，而是通过 `vector_stores` 配置表（[`migrations/versioned/000032_vector_stores.up.sql`](../migrations/versioned/000032_vector_stores.up.sql)）支持多个引擎并存：

```
vector_stores 表
├─ id
├─ engine           （milvus / opensearch / pgvector / ...）
├─ config           （jsonb：连接参数、索引参数）
└─ enabled

knowledge_bases 表
├─ vector_store_id  （绑定到某个 vector store）
└─ ...
```

- **一个 KB 绑定一个 vector store**（避免跨引擎查询）。
- 不同 KB 可以用不同引擎（如生产用 Milvus，测试用 PG pgvector）。
- 引擎适配层：`internal/infrastructure/vectorstore/`。

#### PG pgvector 路径

[`migrations/versioned/000002_embeddings.up.sql`](../migrations/versioned/000002_embeddings.up.sql) 定义了 PG 自带的 embeddings 表：

- `halfvec` 列存储向量（half precision 节省空间）
- HNSW 索引（3584 维 / 798 维，对应不同 embedder）
- BM25 索引使用 `chinese_lindera` 分词器（中文友好）

> 这条路径让单机部署也能跑 RAG（不需要部署独立向量库），但生产规模建议用 Milvus/OpenSearch。

### 4.4 派生关系：为什么说"chunks 是真相"

```
chunks 表（PG，真相）
    │
    ├──→ 向量库（milvus/opensearch/pgvector）：存 chunk_id → embedding
    │
    └──→ BM25 索引：存 chunk_id → tokenized content
```

- 写入路径：每写一个 chunk，按需同步写入向量库和 BM25。
- 删除路径：删除 chunk 时同步删除向量库和 BM25 中的对应项。
- **重建能力**：向量库和 BM25 都可以从 `chunks` 表完全重建（重新跑一遍 embed/索引）。
- 这与 GBrain 的设计不同——GBrain 的 fact/take 含主观判断，不一定能从 page 重建。详见 [GBrain 剖析第 6 节](../../知识库设计/GBrain知识库设计剖析.md#6-与-weknora-设计的对比)。

---

## 5. 检索：分区、归一化、RRF 融合、（可选）Rerank

主入口：[`internal/application/service/knowledgebase_search.go`](../internal/application/service/knowledgebase_search.go)。

### 5.1 三向分区

[`knowledgebase_search.go:334-348`](../internal/application/service/knowledgebase_search.go#L334) 把传入的 KB ID 列表分成三组：

```
输入：kb_ids[]
   │
   ↓
 ┌──────────────────────────────────────────────────────────┐
 │  遍历每个 KB，按 Type 和 IndexingStrategy 投影：          │
 │                                                          │
 │  if Type == faq:                                         │
 │      faqVectorKBIDs.append(kb.id)                        │
 │  else:                                                   │
 │      if VectorEnabled:  docVectorKBIDs.append(kb.id)     │
 │      if KeywordEnabled and Type != faq:                  │
 │              docKeywordKBIDs.append(kb.id)               │
 └──────────────────────────────────────────────────────────┘
   │
   ↓
 三组并行召回：
 ┌── faqVectorKBIDs ──→ 仅向量召回
 │
 ├── docVectorKBIDs ──→ 向量召回
 │
 └── docKeywordKBIDs ─→ BM25 关键词召回
```

> **关键事实**：FAQ KB **被硬编码排除在关键词索引之外**（[`knowledgebase_search.go:346`](../internal/application/service/knowledgebase_search.go#L346)）——即使 KB 启用了 `KeywordEnabled`，FAQ 也不会进 BM25。

#### FAQ 为什么不进关键词索引

| 原因 | 说明 |
|---|---|
| **QA 太短** | FAQ 的"问题"通常 10-30 字，BM25 的 IDF 加权效果差，分词后词频信号微弱 |
| **语义模糊** | FAQ 设计就是为了"问非所学"——同义改写、口语化、缩写都常见，关键词命中率低 |
| **向量更擅长** | FAQ 的语义对齐恰恰是向量的强项（同义、近义都能映射到相近向量空间） |
| **避免污染** | 文档场景下，"FAQ 退货政策"和"产品规格文档"是两种检索需求，混在一起会互相干扰 |

### 5.2 分数归一化

[`internal/application/service/retriever/normalizer.go`](../internal/application/service/retriever/normalizer.go) 的 `ScoreNormalizer` 接口：

```
不同向量引擎返回的原始分数（raw score）：
  Milvus     ：[-1, 1]   余弦距离
  OpenSearch ：[0, 1]    （1 + cos）/ 2
  PG pgvector：[0, 1]    1 - 余弦距离
  ...

           ↓ ScoreNormalizer.Normalize(rawScore, engine)

归一化到 [0, 1]：
  Milvus     ：(rawScore + 1) / 2
  OpenSearch ：raw（已归一）
  PG pgvector：raw（已归一）
  ...
```

> **关键事实**：**仅对向量分数归一化，BM25 分数原样透传**。这是因为不同引擎的向量分数必须统一量纲才能融合；而 BM25 是单一引擎（PG），不需要归一化跨引擎。

### 5.3 RRF 融合

[`internal/application/service/knowledgebase_search_fusion.go`](../internal/application/service/knowledgebase_search_fusion.go) 实现两路（向量 + 关键词）融合。

#### 公式

```
RRF_score(chunk) = vectorWeight / (k + vectorRank)
                + keywordWeight / (k + keywordRank)
```

- `vectorRank`：该 chunk 在向量召回结果中的排名（1-based）
- `keywordRank`：该 chunk 在关键词召回结果中的排名（1-based）
- `k`：平滑常数（典型 60），防止排名 1 的 chunk 主导总分
- `vectorWeight / keywordWeight`：可配置的权重（默认 1:1）

#### 为什么用 RRF 而不是加权求和

| 选项 | 问题 |
|---|---|
| 加权求和（vectorScore * w1 + keywordScore * w2） | 即使向量分数已归一化，BM25 分数仍可能远大于 1（取决于文档长度、词频），加权会被 BM25 主导 |
| 仅取并集 + 各自排序 | 失去分数信息，无法区分"两边都靠前"和"一边靠前" |
| **RRF（倒数秩融合）** | 只看排名不看绝对分数 → 跨引擎、跨量纲都能融合；同时靠前的 chunk 在两路都得到提升 |

#### 去重

`fuseOrDeduplicate`：同一个 chunk_id 同时被向量与关键词召回时，按 RRF 公式合并分数，**不**重复出现在最终列表里。

### 5.4 Rerank 的位置：在 chat_pipeline，不在 knowledgebase_search

**容易踩坑**的点：rerank **不在** `knowledgebase_search` 内部，而是在 [`internal/application/service/chat_pipeline/`](../internal/application/service/chat_pipeline/) 中作为独立插件。

```
knowledge_search 工具调用
   │
   ↓
knowledgebase_search 服务
   │
   ↓
三向分区 + 召回 + RRF 融合 → top-N（如 N=20）
   │
   ↓ 返回给 chat_pipeline
   │
chat_pipeline 的 Rerank 插件
   │
   ↓
对 top-N 用 cross-encoder 模型重排 → top-k（如 k=5）
   │
   ↓
拼 prompt 给 LLM
```

#### 为什么这样切分

| 原因 | 说明 |
|---|---|
| **职责单一** | `knowledgebase_search` 只管"召回 + 融合"，不绑定 rerank 实现；`chat_pipeline` 是策略层，可以决定是否启用 rerank、用哪个 reranker 模型 |
| **可插拔** | rerank 是 chat_pipeline 的插件，可以独立启用/禁用、换模型，不影响检索逻辑 |
| **延迟可控** | rerank 是 GPU 密集操作，放在最末段，只对 top-N（已大幅缩减）做，避免对全库计算 |
| **同样可被 Agent 工具使用** | `knowledge_search` 工具直接调 `knowledgebase_search`，不会被强制走 rerank；rerank 只在 chat 流程中默认启用 |

---

## 6. 数据表清单

WeKnora 的 RAG 路径涉及以下 PostgreSQL 表（按职责分组）：

### 6.1 KB 与 Knowledge 元数据

| 表 | 作用 | 迁移文件 |
|---|---|---|
| `knowledge_bases`     | KB 容器（Type、IndexingStrategy、vector_store_id 等） | `000000_init` |
| `knowledges`          | 一次文档/QA 摄入（status、pending_subtasks_count、attempt） | `000000_init` + `000056` |
| `vector_stores`       | 多向量库引擎配置 | `000032_vector_stores` |
| `embeddings`          | PG pgvector 路径的向量表（halfvec + HNSW + BM25） | `000002_embeddings` |

### 6.2 分块与图谱

| 表 | 作用 | 迁移文件 |
|---|---|---|
| `chunks`              | **核心真相**：所有分块（含父子、entity、relationship） | `000000_init` |
| `knowledge_tags`      | Knowledge 级标签 | `000000_init` |
| `knowledge_tag_relations` | 标签关系（用于跨 KB 联合查询） | 后期迁移 |

> **没有独立的 `graph_entities` / `graph_relations` 表**——图谱数据混在 `chunks` 表里，用 `chunk_type='entity'` 和 `chunk_type='relationship'` 区分。可选的 Neo4j 后端只是查询加速层，不是事实来源。

### 6.3 摄取流水线追踪

| 表 | 作用 | 迁移文件 |
|---|---|---|
| `knowledge_processing_spans` | 摄入 span 树（root/stage/subspan/generation） | `000055` |
| `task_pending_ops`           | asynq 异步任务待办 | `000041` |
| `task_dead_letters`          | asynq 死信队列 | `000041` |

### 6.4 用户偏好

| 表 | 作用 | 迁移文件 |
|---|---|---|
| `user_kb_pins`        | 用户置顶的 KB（前端快捷入口） | 后期迁移 |

---

## 7. 常见误解澄清

| 误解 | 事实 |
|---|---|
| "父子分块都进向量库" | 仅**子分块**进向量库；父分块**只**写入 `chunks` 表，召回子分块时作为上下文返回 |
| "Summary/Question-Gen 是串行的" | Summary、Question-Gen、Wiki-Ingest、Graph-Extract 是**并行**扇出，相互独立 |
| "Knowledge 状态只有 pending/completed" | 实际有 4 个状态：`pending` → `processing` → `finalizing` → `completed`（外加 `failed`） |
| "FAQ 不能上传文件" | FAQ **可以**上传，但仅限结构化格式（`.json/.csv/.xlsx/.xls`），前端解析。详见 [kb-architecture.md 第 5.1 节](./kb-architecture.md#51-faq-的上传机制重要澄清) |
| "WeKnora 有独立的图谱表" | 没有。`chunk_type='entity'/'relationship'` 都在 `chunks` 表里，可选 Neo4j 只是查询加速层 |
| "Rerank 是检索的一部分" | Rerank 是 `chat_pipeline` 的独立插件，**不在** `knowledgebase_search` 内部 |
| "BM25 分数也会被归一化" | 不会。`ScoreNormalizer` 仅对向量分数归一化；BM25 原样透传，靠 RRF 的"按排名融合"避免量纲问题 |
| "三向分区是为了性能" | 三向分区是为了**语义隔离**（FAQ vs 文档的语义空间不同），性能是副作用 |
| "向量库是真相" | `chunks` 表才是真相，向量库和 BM25 都是 `chunks` 的派生索引，可完全重建 |

---

## 8. 关键文件索引

### 摄取

| 文件 | 内容 |
|---|---|
| `internal/application/service/knowledge_process.go` | 摄取主流水线（5 串行阶段 + 4 并行扇出） |
| `internal/application/service/post_process.go`      | PostProcess 阶段入口（触发 4 个并行扇出） |
| `internal/infrastructure/docparser/`                | DocReader 解析器（PDF/Word/HTML → markdown + 图片） |
| `internal/application/service/knowledge_faq_import.go` | FAQ 摄入（前端解析后的 batch upsert） |

### 检索

| 文件 | 内容 |
|---|---|
| `internal/application/service/knowledgebase_search.go`       | 三向分区（faq/doc-vector/doc-keyword） |
| `internal/application/service/knowledgebase_search_fusion.go` | RRF 融合、去重 |
| `internal/application/service/retriever/normalizer.go`       | `ScoreNormalizer`（仅归一化向量分数） |
| `internal/application/service/chat_pipeline/`                | chat 流水线（含 rerank 插件） |

### 类型与常量

| 文件 | 内容 |
|---|---|
| `internal/types/chunk.go`            | `ChunkType*` 常量（12 种） |
| `internal/types/knowledgebase.go`    | `KnowledgeBase`、`IndexingStrategy` 投影方法 |
| `internal/types/faq.go`              | `FAQChunkMetadata`、`FAQEntry` |

### 数据库迁移

| 文件 | 内容 |
|---|---|
| `migrations/versioned/000000_init.up.sql`                        | `knowledge_bases` / `knowledges` / `chunks` 表 |
| `migrations/versioned/000002_embeddings.up.sql`                  | PG pgvector 路径（halfvec + HNSW + BM25） |
| `migrations/versioned/000032_vector_stores.up.sql`               | 多向量库配置表 |
| `migrations/versioned/000055_knowledge_processing_spans.up.sql`  | 摄入 span 追踪 |
| `migrations/versioned/000056_knowledge_pending_subtasks.up.sql`  | Knowledge 状态机扩展（`pending_subtasks_count`） |

---

## 附录：与其他架构文档的对应

- KB 容器、IndexingStrategy、Type、Document/FAQ/Wiki 子模式 → 见 [kb-architecture.md](./kb-architecture.md)
- Wiki 独立检索路径（去抖动、Map-Reduce、PG 全文索引） → 见 [wiki-architecture.md](./wiki-architecture.md)
- 跨项目对比（与 GBrain 的存储后端、多租户、结构化记忆等差异） → 见 [GBrain 剖析第 6 节](../../知识库设计/GBrain知识库设计剖析.md#6-与-weknora-设计的对比)

---

*本文档基于代码状态：2026-07-05 / commit `7d8a80ae`。*
