# WeKnora Wiki 系统架构文档

> 本文档系统整理 WeKnora 项目中 Wiki 子系统的设计:存储结构、数据模型、文档摄入流程、图片处理、与向量数据的关系、并发模型,以及关键的设计权衡。
>
> 适用于想要理解、扩展或调试 Wiki 功能的开发者。

---

## 目录

- [1. 概述](#1-概述)
- [2. 整体架构](#2-整体架构)
- [3. 存储层](#3-存储层)
  - [3.1 PostgreSQL(真相来源)](#31-postgresql真相来源)
  - [3.2 Redis(短时状态)](#32-redis短时状态)
  - [3.3 对象存储(图片)](#33-对象存储图片)
- [4. 数据模型](#4-数据模型)
  - [4.1 表关系图](#41-表关系图)
  - [4.2 wiki_pages 字段详解](#42-wiki_pages-字段详解)
  - [4.3 其他表字段速查](#43-其他表字段速查)
  - [4.4 真实 wiki page 示例](#44-真实-wiki-page-示例)
- [5. 文档 → Wiki 转换流程](#5-文档--wiki-转换流程)
- [6. 图片处理链路](#6-图片处理链路)
- [7. Wiki 与向量数据的关系](#7-wiki-与向量数据的关系)
- [8. 批处理与并发模型](#8-批处理与并发模型)
- [9. 关键设计权衡](#9-关键设计权衡)
- [10. 关键文件索引](#10-关键文件索引)

---

## 1. 概述

WeKnora 的 Wiki 是一个 **LLM 驱动、自动生成、可累积的知识库体系**:

- 用户上传文档 → LLM 自动抽取实体/概念/摘要 → 生成互相链接的 markdown 页面
- 页面持久化在 PostgreSQL,可被 Agent 通过 `wiki_search` / `wiki_read_page` 工具检索
- **与向量检索体系基本独立**(见第 7 节)

**核心特征**:
- 自动生成,无需手写
- 双向链接(`[[slug|display]]` 语法)
- 跨文档合并(同一实体的多次提及合并到同一页)
- 版本化(用户可见变更才 +1)
- 软删除 + 操作日志(append-only 事件流)

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                         用户上传文档                              │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  DocReader 解析      │   (PDF/Word/HTML → markdown)
              │  + ImageResolver     │   (图片上传对象存储)
              └──────┬───────────────┘
                     │
        ┌────────────┴───────────────┐
        ▼                            ▼
┌─────────────────┐         ┌────────────────────┐
│  chunks 表      │         │  task_pending_ops  │
│  (向量化检索)   │         │  (wiki 入队)       │
└─────────────────┘         └─────────┬──────────┘
                                      │ 30s 去抖动
                                      ▼
                            ┌────────────────────┐
                            │  asynq 异步任务    │
                            │  wiki ingest batch │
                            └──────┬─────────────┘
                                   │
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
          ┌──────────┐      ┌────────────┐     ┌─────────────┐
          │ Map 阶段 │      │ Dedup 阶段 │     │ Reduce 阶段 │
          │ 并行抽   │  →   │ 跨文档合并 │  →  │ 写 wiki_pages│
          │ 实体/摘要│      │ 单次 LLM   │     │ + 后处理    │
          └──────────┘      └────────────┘     └─────────────┘
                                                   │
                                                   ▼
                                         ┌──────────────────┐
                                         │  PostgreSQL      │
                                         │  wiki_pages      │
                                         │  wiki_folders    │
                                         │  wiki_log_entries│
                                         └──────────────────┘
```

---

## 3. 存储层

### 3.1 PostgreSQL(真相来源)

Wiki 系统持久化涉及 **7 张表 + 2 个列**。

#### 4 张 wiki 专属表

| 表名 | 迁移 | 作用 |
|---|---|---|
| `wiki_pages` | 000037, 000061 | 页面本身,LLM 生成的 markdown |
| `wiki_folders` | 000037, 000061 | 目录节点(邻接表树) |
| `wiki_page_issues` | 000037 | 页面问题标记(LLM/用户/lint 标记) |
| `wiki_log_entries` | 000040 | 操作日志(append-only 事件流) |

#### 2 张通用任务队列表(wiki 借用)

| 表名 | 迁移 | 作用 |
|---|---|---|
| `task_pending_ops` | 000041 | 待办 op 持久化队列(替代旧版 Redis list) |
| `task_dead_letters` | 000041 | 死信归档(永久保留) |

#### KB 主表上的 2 个 JSONB 列

| 列名 | 作用 |
|---|---|
| `knowledge_bases.wiki_config` | 每 KB 的 wiki 配置(模型、批次大小、提取粒度) |
| `knowledge_bases.indexing_strategy` | 4 个独立开关(`vector_enabled` / `keyword_enabled` / `wiki_enabled` / `graph_enabled`) |

> **注意**:`indexing_strategy.wiki_enabled = false` 时,wiki 管线完全不触发;但向量/关键词索引可以独立启用。**Wiki 与向量是可独立开启的两套体系**。

### 3.2 Redis(短时状态)

Redis 在 Wiki 系统**只做两件事**,都不存业务真相。

| Key 格式 | 作用 | TTL |
|---|---|---|
| `wiki:active:<kbID>` | 批处理互斥锁(`SETNX` "1") | 60s,每 20s 续约 |
| `wiki:deleted:<kbID>:<knowledgeID>` | 删除墓碑 | 1 小时 |

**历史变迁**:旧版用 `wiki:pending:<kbID>` Redis list 做待办队列,但 24h TTL 在大 KB(4w+ 文档)上会丢任务,已迁移到 `task_pending_ops` 表(`migrations/versioned/000041`)。

**Lite 模式**:无 Redis 时,锁退化为进程内 `sync.Map`(`liteLocks`),仅单进程可用。

### 3.3 对象存储(图片)

图片存储在 S3 / MinIO(取决于 `StorageEngineConfig`)。`wiki_pages.content` 里的 `![caption](url)` URL 指向对象存储,**wiki page 本身只存 URL,不存图片字节**。

详见 [第 6 节:图片处理链路](#6-图片处理链路)。

---

## 4. 数据模型

### 4.1 表关系图

```
knowledge_bases (主表)
  ├─ wiki_config (列) ──────┐
  └─ indexing_strategy (列) │ wiki_enabled = true 才会触发
                            │
                            ▼
   ┌──────────────────────────────────────────────┐
   │            wiki_folders (目录树)              │
   │  id ◄────────────────┐                       │
   │  parent_id ──────────┘  (自引用邻接表)        │
   │  knowledge_base_id ───→ knowledge_bases.id    │
   └──────────────────────────────────────────────┘
                            ▲
                            │ folder_id (FK)
                            │
   ┌──────────────────────────────────────────────┐
   │             wiki_pages (页面)                 │
   │  slug (KB 内唯一)                              │
   │  parent_slug ──→ 自引用                        │
   │  folder_id ────→ wiki_folders.id              │
   │  source_refs ──→ knowledge.id (软引用)         │
   │  chunk_refs ───→ chunks.id (软引用)            │
   │  in_links ────→ wiki_pages.slug (软引用)       │
   │  out_links ───→ wiki_pages.slug (软引用)       │
   └──────────────────────────────────────────────┘
                            ▲
                            │ slug (软引用)
                            │
   ┌──────────────────────────────────────────────┐
   │         wiki_page_issues (问题)               │
   │  slug ────────────→ wiki_pages.slug           │
   │  suspected_knowledge_ids ──→ knowledge.id     │
   └──────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────┐
   │       wiki_log_entries (操作日志)              │
   │  knowledge_base_id ──→ knowledge_bases.id     │
   │  knowledge_id ───────→ knowledge.id           │
   │  pages_affected ─────→ wiki_pages.slug (JSONB)│
   └──────────────────────────────────────────────┘

   ┌──────────────────────────────────────────────┐
   │     task_pending_ops / task_dead_letters     │
   │  scope_id ─────────→ knowledge_bases.id      │
   │  (task_type="wiki:ingest" 的行就是 wiki 任务) │
   └──────────────────────────────────────────────┘
```

### 4.2 wiki_pages 字段详解

#### 标识字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | VARCHAR(36) PK | UUID |
| `tenant_id` | BIGINT | 多租户隔离 |
| `knowledge_base_id` | VARCHAR(36) | 所属 KB |
| `slug` | VARCHAR(255) | **KB 内唯一**,带类型前缀,如 `entity/acme-corp` |
| `title` | VARCHAR(512) | 人类可读标题 |
| `aliases` | JSONB | 别名数组(缩写/全称/翻译/俗称) |
| `page_type` | VARCHAR(32) | 7 种类型,见下表 |

#### page_type 取值

| 类型 | 含义 | 自动/手动 |
|---|---|---|
| `summary` | 每份上传文档的摘要页(slug = `summary/<knowledgeID>`) | 自动 |
| `entity` | LLM 抽取的实体(人/组织/地点/产品/技术/事件) | 自动 |
| `concept` | LLM 抽取的概念(方法论/理论/主题) | 自动 |
| `index` | KB 索引页(KB 内 1 个,slug = `"index"`) | 自动 |
| `log` | KB 操作日志页(KB 内 1 个,slug = `"log"`) | 自动 |
| `synthesis` | 综合分析页 | 手动(Agent 通过 `wiki_write_page` 创建) |
| `comparison` | 对比页 | 手动 |

#### 内容字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `content` | TEXT | 完整 markdown 正文(含 `[[slug\|display]]` 链接、图片、标题) |
| `summary` | TEXT | 一句话摘要(15–40 字),用于索引列表展示 |
| `status` | VARCHAR(32) | `draft` / `published` / `archived` |

#### 目录归属字段(000061 加的层级结构)

| 字段 | 类型 | 说明 |
|---|---|---|
| `folder_id` | VARCHAR(36) | **唯一可信来源**,指向 `wiki_folders.id`(`""` = wiki 根) |
| `category_path` | JSONB | 冗余缓存,如 `["AI 应用", "RAG"]` |
| `wiki_path` | VARCHAR(1024) | 冗余缓存,可排序全路径 |
| `depth` | INT | 冗余缓存,`len(category_path)` |
| `parent_slug` | VARCHAR(255) | 旧字段(已被 `folder_id` 取代,保留兼容) |
| `sort_order` | INT | 同级排序权重 |

> **设计原则**:"一个真相 + 三个冗余缓存"。`folder_id` 是真相,`category_path` / `wiki_path` / `depth` 都从它派生,让列表/过滤查询不用 JOIN `wiki_folders`。

#### 引用与链接字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `source_refs` | JSONB | **文档级溯源**,格式 `["<knowledgeID>\|<docTitle>", ...]` |
| `chunk_refs` | JSONB | **chunk 级溯源**,UUID 数组(`summary` 类页面通常为空) |
| `in_links` | JSONB | 反向链接(哪些 slug 链向我,自动维护) |
| `out_links` | JSONB | 正向链接(我链接到哪些 slug,从 content 扫 `[[...]]` 提取) |

#### 元数据字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `page_metadata` | JSONB | 自由扩展(标签、自定义元数据) |
| `version` | INT | **仅当用户可见字段(title/content/summary/page_type/status)变更才 +1**。死链清理、跨链注入、状态同步不 +1 |
| `created_at` / `updated_at` / `deleted_at` | TIMESTAMPTZ | 时间戳,GORM 软删除 |

### 4.3 其他表字段速查

#### wiki_folders

```sql
id              VARCHAR(36) PK
tenant_id       BIGINT
knowledge_base_id VARCHAR(36)   → knowledge_bases.id
parent_id       VARCHAR(36)     → wiki_folders.id (自引用)
name            VARCHAR(255)    同级兄弟内唯一
path            VARCHAR(1024)   materialized 路径,"/" 分隔
depth           INT
sort_order      INT
created_at / updated_at / deleted_at
```

#### wiki_page_issues

```sql
id                    VARCHAR(36) PK
tenant_id / knowledge_base_id
slug                  VARCHAR(255)    → wiki_pages.slug
issue_type            VARCHAR(50)     dead_link / hallucination / outdated ...
description           TEXT
suspected_knowledge_ids JSONB
status                VARCHAR(20)     pending / resolved / ignored
reported_by           VARCHAR(100)    agent / lint / user
created_at / updated_at / deleted_at
```

#### wiki_log_entries(append-only 事件流)

```sql
id                BIGSERIAL PK       单调自增,做游标分页
tenant_id / knowledge_base_id
action            VARCHAR(32)        ingest / retract / edit
knowledge_id      VARCHAR(36)        → knowledge.id (可空)
doc_title         TEXT               事件发生时的文档标题(快照)
summary           TEXT               一句话变更说明
pages_affected    JSONB              [{slug, title}, ...]
created_at        TIMESTAMPTZ
```

> **关键设计**:每个事件一行 INSERT,append-only。取代了旧版"把整个日志拼成 markdown 塞回 `wiki_pages` 一行的 content"(slug='log')—— 那种写法每次事件都要重写整列 TEXT,O(n²) 写放大。

#### task_pending_ops(通用)

```sql
id          BIGSERIAL PK
tenant_id   BIGINT
task_type   VARCHAR(64)   -- "wiki:ingest"
scope       VARCHAR(32)   -- "knowledge_base"
scope_id    VARCHAR(64)   -- → knowledge_bases.id
op          VARCHAR(32)   -- ingest / retract
dedup_key   VARCHAR(128)  -- 通常是 knowledge_id
payload     JSONB         -- WikiPendingOp 序列化
fail_count  INT           -- in-batch 重试计数
enqueued_at / claimed_at
```

#### task_dead_letters(通用,无 TTL)

```sql
id          BIGSERIAL PK
tenant_id / task_type / scope / scope_id
related_id  VARCHAR(64)   -- wiki 用 knowledge_id 填
payload     JSONB         -- 失败时的原始 payload
last_error  TEXT
fail_count  INT
failed_at   TIMESTAMPTZ
```

### 4.4 真实 wiki page 示例

假设上传了一份 Acme 公司的 PDF 介绍,LLM 抽取出"Acme Corp"实体 + "RAG"概念。最后 `wiki_pages` 表里**这一行**长这样:

#### 表行视图

```
id              = "8f2a1c..."
tenant_id       = 1
knowledge_base_id = "kb-001"
slug            = "entity/acme-corp"
title           = "Acme Corporation"
page_type       = "entity"
status          = "published"
aliases         = ["Acme", "Acme Corporation"]

content         = <见下面 markdown>
summary         = "一家专注于企业级 AI 解决方案的科技公司。"

folder_id       = "folder-3f"
category_path   = ["组织", "科技公司"]
wiki_path       = "entity/组织/科技公司/acme-corporation"
depth           = 2
sort_order      = 0

source_refs     = ["k-2024-pdf|Acme 公司介绍.pdf"]
chunk_refs      = ["chunk-uuid-1", "chunk-uuid-2", "chunk-uuid-3"]

in_links        = ["summary/k-2024-pdf", "concept/rag"]
out_links       = ["concept/rag", "concept/llm"]

version         = 1
created_at      = 2026-07-01 10:00:00
updated_at      = 2026-07-01 10:00:00
```

#### content 字段里的实际内容

```markdown
**Acme Corporation**(简称 **Acme**)是一家成立于 2020 年的科技公司,专注于企业级 AI 产品。

## 主要业务

公司的旗舰产品是基于 [[concept/rag|检索增强生成]] 技术构建的企业知识库平台,
集成了大语言模型(参见 [[concept/llm|大语言模型]])能力。

![产品架构图](minio://tenant-1/wiki-images/uuid-abc.png)

## 关键事实

- 创立时间:2020 年
- 员工规模:500+
- 总部:上海
```

> `[[concept/rag|检索增强生成]]` 是 wiki 的双向链接语法。`out_links` 由正则扫 content 提取;`concept/rag` 页的 `in_links` 会被自动加上 `entity/acme-corp`。

---

## 5. 文档 → Wiki 转换流程

### 5.1 触发与去抖动

```
文档上传 → 解析 chunks → KnowledgePostProcess 编排
            ↓
            检查 kb.IndexingStrategy.WikiEnabled && len(textChunks) > 0
            ↓ 满足
            EnqueueWikiIngest (wiki_ingest.go:297)
              ├─ 写一行到 task_pending_ops
              └─ 入 asynq 任务,ProcessIn=30s(去抖动)
```

### 5.2 Map-Reduce 管道

30s 后 worker 拉起 `ProcessWikiIngest`(`wiki_ingest_batch.go:55`):

```
1. Redis SetNX 抢 KB 级"批处理锁" wiki:active:<kbID>
   ├─ 抢到 → 继续处理
   └─ 抢不到 → 返回 ErrWikiIngestConcurrent,asynq 走短重试(15s 后再来)

2. peek batchSize 个 op(默认 5,可配 kb.WikiConfig.IngestBatchSize)

3. Map 阶段(并行,errgroup 限制默认 10):
   - LLM 抽实体/概念(WikiCandidateSlugPrompt + WikiChunkCitationPrompt)
   - LLM 生成文档 summary 页(WikiSummaryPrompt)
   - chunk 级引用匹配

4. Dedup 阶段(单次 LLM 调用):
   - pg_trgm 相似度预过滤(FindSimilarPages,顶部 K 个候选)
   - LLM 决定合并映射(WikiDeduplicationPrompt)
   - 校验:同类型前缀 + 候选集存在性

5. Reduce 阶段(并行,errgroup 限制默认 10):
   - 按 slug 创建/更新 wiki_page(WikiPageModifyPrompt)
   - 应用 PlannedFolderID(由 taxonomy 规划阶段决定)

6. 后处理:
   - 死链清理(cleanDeadLinks)
   - 跨链注入(injectCrossLinks)
   - 草稿 → 发布(publishDraftPages)
   - 重建索引页 intro(rebuildIndexPage)
   - 写操作日志(wiki_log_entries)
```

### 5.3 失败与重试

- **LLM 调用失败**:`generateWithTemplate` 内部最多 3 次,指数退避(2s/4s/8s)
- **整 batch 失败**:asynq 最多 10 次重试
- **单 op 失败**:`requeueFailedOps` 最多 5 次,超限进 `task_dead_letters`

### 5.4 删除时的反向流程

文档删除 → `cleanupWikiOnKnowledgeDelete`(`knowledge_delete.go:147`):

1. 写 Redis 墓碑 `wiki:deleted:<kbID>:<knowledgeID>`(1h TTL)
2. 入 `EnqueueWikiRetract` 任务
3. Worker 处理 retract:
   - 单源页面 → 删除
   - 多源页面 → LLM 调用移除该文档贡献的部分
4. 清理 `chunk_refs`、`source_refs`、`in_links`

墓碑的作用:让 in-flight 的 wiki ingest 任务**快速跳过**已删除文档,不用反复打数据库。

---

## 6. 图片处理链路

### 6.1 整体流程

```
原始文档(PDF/Word/HTML)
    ↓ DocReader 解析
markdown + ImageRefs(内联 base64 / 外链 URL)
    ↓ ImageResolver.ResolveAndStore (knowledge_process.go:2997)
    ├─ 内联 data URI     → 上传对象存储
    ├─ HTML 内嵌 base64  → 上传对象存储
    ├─ 裸 base64         → 上传对象存储
    └─ http(s) 外链      → ResolveRemoteImages 下载后上传
    ↓
markdown 中的图片占位符替换为 provider:// URL
    ↓
    ├─→ 写入 chunks.content(向量化管线消费)
    └─→ 作为 wiki LLM 的 {{.Content}} 输入
        ↓ LLM 按 prompt 规则"图片 URL 是不透明 token,原样保留"
        ↓
    生成 wiki content(包含同样的 URL)
```

### 6.2 关键代码

| 步骤 | 文件 |
|---|---|
| 图片抽取 + 上传 | `internal/infrastructure/docparser/image_resolver.go` |
| 调用入口 | `internal/application/service/knowledge_process.go:2991` |
| URL mask/unmask(防 LLM 篡改) | `internal/application/service/wiki_ingest.go:2120` |
| VLM OCR + Caption(图片描述子 chunk) | `internal/application/service/image_multimodal.go` |

### 6.3 图片 URL 防篡改机制

LLM prompt 渲染前,`maskTemplateDataImageURLs` 把所有图片 URL 替换为 `wkimg:0001` 之类的占位 token;LLM 输出后 `unmaskImageURLs` 还原。**双重保险**:就算 LLM 想编 URL 也只会编出无效 token,被清理成空串,不会污染存储。

### 6.4 过滤策略

- 宽高 < 64px 或文件 < 512 字节 → 视为图标,丢弃(`isIconImage`)

### 6.5 第二条线:VLM OCR + Caption

`image_multimodal.go` 还会:

```
图片 → VLM(视觉模型)→ OCR 文本 + Caption 描述
     → 写入 chunks 表的子 chunk(image_ocr / image_caption 类型)
     → reconstructEnrichedContent() 把这些文本拼回 content
     → wiki LLM 能"看到"图片内容,可在 wiki page 描述图片讲了什么
```

---

## 7. Wiki 与向量数据的关系

### 7.1 核心结论:**基本完全分开**

| 维度 | 向量/关键词检索 | Wiki |
|---|---|---|
| 数据表 | `chunks` | `wiki_pages` |
| 索引 | embedding 向量 + BM25 | PostgreSQL `to_tsvector` GIN 全文索引 |
| 触发开关 | `vector_enabled` / `keyword_enabled` | `wiki_enabled` |
| 调用路径 | `knowledge_search` 工具 | `wiki_search` / `wiki_read_page` 工具 |
| 检索实现 | 向量召回 + rerank | `wikiPageRepository.Search` → `to_tsvector` 查询 |

**Wiki page 默认不会被向量化进 chunks 表**。

### 7.2 预留但未启用的结合点

代码里有三处"半成品"痕迹,说明设计上预留过结合点,但当前没有实际写入逻辑:

1. `internal/types/chunk.go:39` 定义了 `ChunkTypeWikiPage = "wiki_page"`
2. `wiki_page.go:926` 有 `deleteChunkForPage`(删除 wiki 时清理 `"wp-"+page.ID`),但**整个 codebase 找不到对应的 `upsertChunkForPage`**
3. `chat_pipeline/wiki_boost.go` 准备好给 `ChunkTypeWikiPage` chunk 加 1.3× 权重,但因为没人写入这种 chunk,该插件实际是空跑的

### 7.3 当前检索路径

```
用户提问
   ↓
Agent 决策
   ├─ 走 wiki  → wiki_search (PG to_tsvector 全文索引)
   ├─ 走向量  → knowledge_search (向量召回 + rerank)
   └─ 走关键词 → grep_chunks (BM25)
```

`internal/application/service/agent_service.go` 的 `kbRetrievalMode` 决定走哪条路径。

---

## 8. 批处理与并发模型

### 8.1 关键常量

| 常量 | 默认值 | 说明 |
|---|---|---|
| `wikiMaxDocsPerBatch` | 5 | 单 batch 处理 op 数 |
| `wikiIngestDelay` | 30s | 上传后去抖动延迟 |
| `wikiMaxFailRetries` | 5 | 单 op in-batch 重试上限 |
| `wikiIngestMaxRetry` | 10 | asynq 任务重试上限 |
| `wikiActiveLockTTL` | 60s | 互斥锁 TTL |
| `wikiActiveLockRenew` | 20s | 锁续约间隔 |
| `wikiLLMMaxAttempts` | 3 | 单次 LLM 调用重试上限 |
| `wikiLLMBackoffBase` | 2s | LLM 重试指数退避基数 |
| `wikiDeletedTTL` | 1h | 删除墓碑 TTL |

### 8.2 同一 KB 内串行化

**"不能并发 batch" 不等于 "不能并发上传"**。

**同一 KB 内**的 wiki ingest 任务被设计成**串行化批处理**,因为:
- **Dedup 必须看"一批"文档才能正确合并**(否则同一实体的不同表面形式会生成多个 page)
- **跨链注入**必须知道 batch 内全部页面才能正确链接

### 8.3 同时上传 N 份文档的实际行为

```
T+0s   两份文档立刻进入解析管线(chunking / 向量 / BM25 全部并行跑)
       wiki 这条线各写一行到 task_pending_ops,各入一个 asynq 任务,ProcessIn=30s

T+30s  worker1 抢 SETNX wiki:active:<kbID> → 成功
       worker2 抢 SETNX → 失败 → ErrWikiIngestConcurrent → asynq 15s 后重试

T+30s  worker1 peek batchSize=5 → 拿到 [A, B] 两份 op
       Map 并行处理 A 和 B
       Dedup 一次性看 A+B 的实体集 → 合并
       Reduce 写入 wiki_pages
       释放 wiki:active:<kbID>

T+45s  worker2 重试,抢到锁 → peek 队列 → 已空 → 直接返回
```

**两份文档被合并在同一个 batch 里处理**,而不是被丢掉或永久排队。这反而是更优的设计:LLM 一次性看两份相关文档,跨文档的实体能正确合并、跨链能正确注入。

### 8.4 超过 batchSize 的真实排队

```
一次上传 12 份文档:
  batch 1 (T+30s):  处理 op[0..4]   5 份
  batch 2 (T+35s):  处理 op[5..9]   5 份  (scheduleFollowUp)
  batch 3 (T+40s):  处理 op[10..11] 2 份
```

每个 batch 处理完后调用 `scheduleFollowUp`(`wiki_ingest_batch.go:29`),检查队列还有剩就再入一个 5s 延迟的 asynq 任务。

### 8.5 跨 KB 完全并行

```
wiki:active:kb-A   ← KB-A 自己的锁
wiki:active:kb-B   ← KB-B 自己的锁
```

不同 KB 的 wiki 任务是**真正并行**的。串行化只在"同一个 KB 内",目的是保证同一份知识库里的页面状态一致。

### 8.6 为什么选 Redis 锁而不是其他方案

| 方案 | 问题 |
|---|---|
| 不加锁,让 batch 并发跑 | Dedup 失效、跨链错乱 |
| 锁到 page slug 级别 | 跨文档合并仍要全局视图,slug 级锁解决不了 |
| Postgres advisory lock | 每次抢锁要打 DB,Redis SETNX 微秒级 |
| **Redis 锁(当前方案)** | 60s TTL + 20s 续约,简单、崩溃自动恢复 |

---

## 9. 关键设计权衡

### 9.1 持久化队列 vs Redis list

**决策**:用 PostgreSQL `task_pending_ops` 取代 Redis list。

**原因**:Redis 24h TTL 在 4w+ 文档 KB 上会丢任务;Postgres 无 TTL,ACID 保证。

**代价**:每次 enqueue / peek / delete 都是 DB 往返,但 wiki 是低频异步任务,可接受。

### 9.2 append-only 事件流 vs 单行 TEXT 日志

**决策**:`wiki_log_entries` 表(每事件一行)取代 `wiki_pages` 表里 slug='log' 的单行 TEXT。

**原因**:旧版每次事件重写整列 TEXT,O(n²) 写放大;新版 INSERT 永远 O(1)。

**代价**:多一张表,但读路径(cursor 分页)反而更便宜。

### 9.3 folder_id 真相 + 三冗余缓存

**决策**:`folder_id` 是目录归属的真相,`category_path` / `wiki_path` / `depth` 都是从它派生的冗余字段。

**原因**:让 `wiki_pages` 单表查询能完成目录浏览、过滤、排序,不用 JOIN `wiki_folders`。

**代价**:写入时要同步维护 4 个字段,但写少读多场景下值得。

### 9.4 version 字段的精细策略

**决策**:**仅**用户可见字段(title/content/summary/page_type/status)变更才 +1;`UpdateAutoLinkedContent`(死链清理、跨链注入)和 `UpdateMeta`(链接维护、状态同步)都不 +1。

**原因**:让 `version` 成为可靠的"页面被人工编辑过"信号,不被机器维护污染。

### 9.5 Wiki 与向量检索分离

**决策**:wiki page 默认不向量化,走独立的 PG 全文索引。

**原因**:
- wiki page 是 LLM 综合产物,已自带语义关联,不需要向量相似度
- 分离让两套体系独立演进,故障域隔离
- 避免重复存储 + 重复计算 embedding

**预留**:`ChunkTypeWikiPage` 类型 + `wiki_boost` 插件为未来"wiki 参与向量召回"留好了接口。

---

## 10. 关键文件索引

### 类型定义

| 文件 | 内容 |
|---|---|
| `internal/types/wiki_page.go` | `WikiPage` / `WikiFolder` / `WikiConfig` / `WikiExtractionGranularity` 等核心类型 |
| `internal/types/wiki_log_entry.go` | `WikiLogEntry` / `WikiLogPageRef` |
| `internal/types/indexing_strategy.go` | `IndexingStrategy`(4 个开关) |
| `internal/types/chunk.go` | `ChunkTypeWikiPage`(预留未启用) |

### 服务层

| 文件 | 内容 |
|---|---|
| `internal/application/service/wiki_ingest.go` | 入队、批处理编排、LLM 调用、图片 URL mask |
| `internal/application/service/wiki_ingest_batch.go` | `ProcessWikiIngest` 主流程、Map/Reduce 编排 |
| `internal/application/service/wiki_ingest_dedup.go` | Dedup 阶段(pg_trgm + LLM) |
| `internal/application/service/wiki_ingest_cite.go` | chunk 引用匹配 |
| `internal/application/service/wiki_ingest_taxonomy.go` | 目录规划 |
| `internal/application/service/wiki_page.go` | `WikiPageService`(CRUD、链接维护) |
| `internal/application/service/wiki_linkify.go` | 跨链注入 |
| `internal/application/service/wiki_lint.go` | lint + AutoFix |
| `internal/application/service/chat_pipeline/wiki_boost.go` | 预留的向量召回加权插件 |

### 仓储层

| 文件 | 内容 |
|---|---|
| `internal/application/repository/wiki_page.go` | `wikiPageRepository`(含全文搜索) |
| `internal/application/repository/wiki_log_entry.go` | 操作日志仓储 |

### Handler 与路由

| 文件 | 内容 |
|---|---|
| `internal/handler/wiki_page.go` | HTTP handler |
| `internal/router/router.go` | 路由注册(搜索 `wiki.GET` 即可) |

### Agent 工具

| 文件 | 内容 |
|---|---|
| `internal/agent/tools/wiki_tools.go` | `wiki_search` / `wiki_read_page` 等工具 |
| `internal/agent/tools/wiki_write_page.go` | Agent 写页面工具 |
| `internal/agent/prompts_wiki.go` | 所有 wiki LLM prompt 模板 |

### 图片处理

| 文件 | 内容 |
|---|---|
| `internal/infrastructure/docparser/image_resolver.go` | 图片抽取 + 上传 |
| `internal/application/service/image_multimodal.go` | VLM OCR + Caption |
| `internal/application/service/knowledge_process.go` | 整体编排(第 2991 行起) |

### 数据库迁移

| 文件 | 内容 |
|---|---|
| `migrations/versioned/000037_wiki_and_indexing.up.sql` | wiki_pages / wiki_folders / wiki_page_issues / wiki_config 列 / indexing_strategy 列 |
| `migrations/versioned/000040_wiki_log_entries.up.sql` | wiki_log_entries |
| `migrations/versioned/000041_task_queue_and_wiki_indexes.up.sql` | task_pending_ops / task_dead_letters + 3 个 wiki_pages GIN 索引 |
| `migrations/versioned/000061_wiki_page_hierarchy.up.sql` | wiki_pages 层级字段 + wiki_folders 重定义 |

---

## 附录:常用调试查询

### 查看某 KB 的 wiki 状态

```sql
-- 总览
SELECT page_type, status, COUNT(*) 
FROM wiki_pages 
WHERE knowledge_base_id = '<kbID>' AND deleted_at IS NULL
GROUP BY page_type, status;

-- 最近更新
SELECT slug, title, version, updated_at 
FROM wiki_pages 
WHERE knowledge_base_id = '<kbID>' AND deleted_at IS NULL
ORDER BY updated_at DESC LIMIT 20;
```

### 查看摄入队列

```sql
-- 待处理 ops
SELECT id, op, dedup_key, fail_count, enqueued_at 
FROM task_pending_ops 
WHERE task_type = 'wiki:ingest' AND scope_id = '<kbID>'
ORDER BY id;

-- 死信
SELECT related_id, last_error, fail_count, failed_at 
FROM task_dead_letters 
WHERE task_type = 'wiki:ingest' AND scope_id = '<kbID>'
ORDER BY failed_at DESC;
```

### 查看操作日志

```sql
SELECT action, doc_title, summary, pages_affected, created_at 
FROM wiki_log_entries 
WHERE knowledge_base_id = '<kbID>'
ORDER BY id DESC LIMIT 50;
```

### 查找死链

```sql
-- 找 out_links 中指向不存在 slug 的页面
SELECT slug, title, out_links
FROM wiki_pages
WHERE knowledge_base_id = '<kbID>'
  AND deleted_at IS NULL
  AND EXISTS (
    SELECT 1 FROM jsonb_array_elements_text(out_links) AS ol(slug)
    WHERE NOT EXISTS (
      SELECT 1 FROM wiki_pages p2
      WHERE p2.knowledge_base_id = '<kbID>'
        AND p2.deleted_at IS NULL
        AND p2.slug = ol.slug
    )
  );
```

---

*本文档基于代码状态:2026-07-03 / commit `7d8a80ae`。*
