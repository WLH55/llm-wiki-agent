# 检索架构（双路径 + IndexingStrategy + wiki chunk boost）

> 状态：Superseded（2026-07-27）<br>
> 本文保留为历史决策记录。其中“Wiki 页面写入 `content_chunks`、参与 RAG 召回并固定加权 1.3”的决策已由 [ADR-0010](./0010-mvp-wiki-rag-separation.md) 取代。MVP 实际采用 Wiki/RAG 两条独立路径，`content_chunks` 不预留 Wiki 内容字段；最终 schema 见 [ADR-0012](./0012-approved-rag-wiki-database-boundaries.md)。

llm_wiki3.0 的检索架构由 **KB 级配置开关 + 两条独立检索路径** 构成：

- **IndexingStrategy 四开关**（KB 创建时配置，决定该 KB 的检索能力）：`vector_enabled` / `keyword_enabled` / `wiki_enabled` / `graph_enabled`。
- **路径 A：wiki_search**——PostgreSQL POSIX 正则 `~*` + 字段权重排序（title=4 / slug=3 / summary=2 / content=1），完全不用向量/embedding/BM25。
- **路径 B：普通 RAG 流水线 + wiki chunk boost**——wiki 页面除了写 `wiki_pages` 表，**还会切块、向量化、写入 `content_chunks` 表**（`chunk_type='wiki_page'`）；普通 RAG 检索（向量 + BM25 + RRF）时这些 wiki chunk 也参与召回，且在 CHUNK_RERANK 阶段被 × 1.3 加权。
- **不做 query 级别模式切换**：用户不在搜索框前选 RAG/Wiki；KB 配置决定能力，检索工具按 KB 类型分发。
- **不做意图分类**：原 [ADR-0006](./0006-agent-runtime-byok.md) §「意图分类（零 LLM）」已弃用——KB 类型由 IndexingStrategy 推断，不需要根据 query 关键词自动路由。

## Context

grilling 过程中讨论过 wiki 检索的两个候选方案，均 rejected：

- **候选 1：双路径联合（RRF 融合 RAG + Wiki 结果）**——rejected。工程复杂度高（跨路径排序调优），且 wiki 与原文 chunk 性质不同，强行联合排序语义模糊。
- **候选 2：query 级别用户手动选模式**——rejected。用户每次搜索都要切模式，体验差；混合 KB 下用户经常不知道该选哪个。

用户最终给出参考设计（一个 Go 实现的知识库系统），全面采纳：① IndexingStrategy 四开关（KB 级别配置）+ ② wiki 也切块向量化 + ③ wiki_search 用正则 + ④ wiki chunk 加权 1.3。本 ADR 落地这套方案。

## Decision

### IndexingStrategy 四开关

`knowledge_bases` 表加 4 个独立布尔字段：

```sql
ALTER TABLE knowledge_bases ADD COLUMN vector_enabled  BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE knowledge_bases ADD COLUMN keyword_enabled BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE knowledge_bases ADD COLUMN wiki_enabled    BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE knowledge_bases ADD COLUMN graph_enabled   BOOLEAN NOT NULL DEFAULT false;
```

| 字段 | 控制的流水线 | 影响 wiki 检索 |
|------|------------|---------------|
| `vector_enabled` | 向量 embedding + 向量检索（pgvector） | wiki chunk 进不进向量库 |
| `keyword_enabled` | BM25 关键词索引（PG 全文 + zhparser） | wiki chunk 进不进 BM25 |
| `wiki_enabled` | 自动生成 wiki 页面（LLM 抽取） | `wiki_pages` 表有没有数据 + wiki chunk 进不进 `content_chunks` |
| `graph_enabled` | 知识图谱抽取（P5+，本 ADR 不展开） | 与 wiki 检索无关，独立 |

**MVP 默认值**：`{vector: true, keyword: true, wiki: true, graph: false}`（混合，让产品差异化能力默认可用）；用户可在 KB 创建时改为纯 RAG（关 `wiki_enabled`）。

### 三种典型 KB 配置

| 配置 | 开关 | 检索行为 |
|------|------|---------|
| **纯 RAG** | `vector=true, keyword=true, wiki=false` | 只有路径 B（无 wiki chunk），普通文档检索 |
| **纯 wiki** | `wiki=true, vector=false`（无 embedding model 绑定） | 只有路径 A（wiki_search 正则）；`knowledge_search` 工具显式拒绝此 KB |
| **混合**（MVP 默认） | `vector=true, keyword=true, wiki=true` | 两条路径都活；wiki chunk 进向量库 + BM25 索引；普通 RAG 检索时 wiki chunk 被 × 1.3 加权 |

### 路径 A：wiki_search（POSIX 正则 + 字段权重）

入口：FastAPI 端点 `GET /api/v1/kb/{kb_id}/wiki/search?q=...&limit=10` + Agent 内部工具 `wiki_search`（[ADR-0006](./0006-agent-runtime-byok.md) Agent Runtime 工具集，MVP 后补充）。

核心 SQL：

```sql
SELECT id, slug, title, summary,
       CASE
         WHEN title   ~* :q THEN 4   -- 标题命中：rank 4
         WHEN slug    ~* :q THEN 3   -- slug 命中：rank 3
         WHEN summary ~* :q THEN 2   -- 摘要命中：rank 2
         WHEN content ~* :q THEN 1   -- 正文命中：rank 1
         ELSE 0
       END AS match_rank
FROM wiki_pages
WHERE kb_id = :kb_id
  AND status != 'archived'
  AND (title ~* :q OR slug ~* :q OR summary ~* :q OR content ~* :q)
ORDER BY match_rank DESC, updated_at DESC
LIMIT :limit;
```

**关键特征**：

- **完全不用向量/embedding/BM25**——PG 内建 POSIX 正则 `~*`（大小写不敏感）。
- **字段权重排序**（title=4 / slug=3 / summary=2 / content=1）——**精确匹配优先**，不是相似度排序。避免"4 万页的 wiki 里搜'王新'时把只是正文提及过王新的'华为'页面排到标题叫'王新'的页面之前"。
- **支持 POSIX 正则特性**：`|` 交替（`stardust|skyvault`）、`.*` 串联（`psionic.*engine`）、`^` 前缀（`^entity/.*`）、`?` 量词等。
- **limit 默认 10，硬上限 50**。
- **中文支持**：`~*` 对中文是字节级子串匹配（中文字符无大小写问题），不需要 zhparser 分词。用户搜"苹果公司"会命中"苹果公司"和"苹果公司总部"。

**设计理由**：

- wiki 的 `title` / `slug` 是 LLM 精心生成的语义标识（如 `entity/acme-corp` / `concept/rag`），结构化程度高，正则精确匹配比模糊向量召回更对路。
- 字段权重排序避免"关键词仅在正文出现"的页面压过"标题就是关键词"的页面。
- 省掉 zhparser 中文分词索引（BM25 那一套）；代价是无词干提取/停用词处理，但 wiki 检索场景不需要。

### 路径 B：普通 RAG + wiki chunk boost 1.3

**wiki 页面也切块向量化**：

LLM 抽取 wiki 页面（写入 `wiki_pages` 表）后，**额外触发切块 + 嵌入流程**（复用文档导入的 chunking + embedding 服务），把 wiki 正文 markdown 切成 chunk、嵌入向量、写入 `content_chunks` 表，`chunk_type='wiki_page'`：

```sql
ALTER TABLE content_chunks ADD COLUMN chunk_type TEXT NOT NULL DEFAULT 'document';
ALTER TABLE content_chunks ADD COLUMN wiki_page_id INT REFERENCES wiki_pages(id) ON DELETE CASCADE;

-- chunk_type 枚举：
--   document      原始文档切块（默认）
--   wiki_page     wiki 页面切块（来自 wiki_pages.body 切分，wiki_page_id 关联源页面）
--   image_ocr     图片 OCR chunk（P4）
--   image_caption 图片 caption chunk（P4）
```

wiki chunk 与普通文档 chunk **同表共存**，参与同一套向量检索（pgvector over `content_chunks.embedding`）+ BM25 检索（PG 全文 over `content_chunks.text`）。

**普通 RAG 检索流程**：

1. 用户 query → 嵌入（query embedding，用查询者 BYOK key）
2. pgvector 检索 top-K chunks（`WHERE chunk_type IN ('document', 'wiki_page')`）
3. PG 全文检索 top-K chunks（BM25，同样两种 chunk_type）
4. RRF 融合两路结果 → 候选集
5. **CHUNK_RERANK 事件触发 wiki_boost plugin**：
   - 检查候选集里有没有 `chunk_type='wiki_page'` 的 chunk（无则跳过）
   - 检查当前 KB 是否开了 `wiki_enabled=true`（纯 RAG KB 永远不触发）
   - 满足条件 → 把 wiki chunk 的 score × **1.3**（硬编码）
   - 按 score 重排（stable sort 保持同分原顺序）
6. 最终 top-K 送 LLM

**boost 触发条件**（不是无脑加权）：

- 结果集里必须真的有 `wiki_page` chunk（line 快速短路）
- 至少一个被检索的 KB 开了 `wiki_enabled=true`

**设计理由**：

- wiki 页面是"LLM 预综合的、交叉引用的知识"，比 raw 文档 chunk 更连贯更可靠，同分时应该优先。
- wiki 又要切块向量化（而不是只靠 wiki_search）是因为：wiki 正文是 markdown 长文，纯靠 title/slug 搜不全；切块让"没指明用 wiki_search"的普通 chat 也能从 wiki 里捞到知识。
- wiki chunk 存到 `content_chunks` 表（与文档 chunk 同表）而不是独立 wiki_chunks 表——切向量库（Milvus/Qdrant，P4）时 wiki chunk 跟着走，boost 逻辑不变。

### KB 类型推断（替代意图分类）

参考系统通过 IndexingStrategy 推断 KB 类型，决定检索工具分发：

- `"rag"` 类型 → KB 有 `vector_enabled=true`
- `"wiki"` 类型 → KB 开了 `wiki_enabled=true`

**检索工具分发**：

| KB 类型 | 可用的检索工具 |
|---------|--------------|
| 纯 RAG（`vector=true, wiki=false`） | 只能 `knowledge_search`（路径 B） |
| 纯 wiki（`wiki=true, vector=false`） | 只能 `wiki_search`（路径 A）；`knowledge_search` 显式拒绝此 KB（无向量库可查，返回 400 + 提示） |
| 混合（`vector=true, wiki=true`） | 两者都可，由 Agent prompt 决定调哪个 |

**替代意图分类**：[ADR-0006](./0006-agent-runtime-byok.md) 原本的"意图分类（零 LLM，5 类路由）"已弃用——用户不再需要系统根据 query 关键词自动路由；KB 类型由 IndexingStrategy 决定，Agent 调工具时显式选 `knowledge_search` 或 `wiki_search`。

### wiki chunk 生命周期

| 事件 | 触发动作 |
|------|---------|
| LLM 抽取生成新 wiki 页面 | 写 `wiki_pages` + 切块 + 嵌入 + 写 `content_chunks`（`chunk_type='wiki_page'`） |
| 手动编辑 wiki 页面（last-write-wins） | 旧 wiki chunks 软删除（`deleted_at`）+ 新 chunks 重嵌入 |
| wiki 页面被删除 | `wiki_pages` 软删除 + 关联 `content_chunks`（通过 `wiki_page_id` ON DELETE CASCADE）软删除 |
| KB 切换嵌入模型（重嵌入） | 文档 chunks + wiki chunks 一起全量重嵌入 |

## Considered Options

- **A. query 级别用户手动选模式**（之前提议）：rejected。用户每次搜索都要切模式，体验差；混合 KB 下用户经常不知道该选哪个；IndexingStrategy 在 KB 创建时决定更符合"产品配置即能力"的设计哲学。
- **B. wiki 不嵌入向量**（之前用户提议过）：rejected。wiki 沦为孤岛——只有显式 `wiki_search` 才能访问；普通 chat 完全用不到 wiki 知识，产品"双路径"价值打折。改为 wiki 也切块嵌入 + boost 加权。
- **C. wiki 检索用 BM25 全文检索**（之前默认）：rejected。wiki 的 title/slug 结构化程度高，BM25 相似度排序会把"只是提及过关键词的页面"排到"标题就是关键词的页面"之前（搜"王新"时"华为"页面排在"王新"页面之前）。改为正则 + 字段权重。
- **D. wiki_search 用 tsvector + ts_query 全文检索（FTS）**：rejected。FTS 不支持任意正则（`stardust|skyvault` 交替做不到）；中文需要 zhparser 分词扩展；正则 `~*` 对中文是字节级子串匹配已够用。
- **E. boost factor 做成可配置**：rejected。1.3 是经验值，暴露给用户增加配置复杂度；硬编码即可，未来需要调参时改代码（参 Open Question A）。
- **F. wiki chunk 独立建表 `wiki_chunks`**：rejected。失去向量库可插拔的统一抽象；与文档 chunk 同表靠 `chunk_type` 区分更优雅，切 Milvus/Qdrant 时逻辑不变。

## Consequences

- **schema 变更**：
  - `knowledge_bases` 表加 4 个 Boolean 字段（IndexingStrategy）
  - `content_chunks` 表加 `chunk_type`（默认 `document`）+ `wiki_page_id`（可空，外键 `wiki_pages.id` ON DELETE CASCADE）
- **wiki 抽取流程改造**：LLM 抽取 wiki 页面后，额外触发切块 + 嵌入流程（复用文档导入的 chunking + embedding 服务）；写入 `content_chunks` 时 `chunk_type='wiki_page'` + `wiki_page_id` 关联源页面。
- **wiki 页面更新**：手动编辑或 LLM 重抽取 → 旧 wiki chunks 软删除 + 新 chunks 重嵌入（与文档更新同模式）。
- **新增 wiki_boost plugin**：注册到 `CHUNK_RERANK` 事件钩子，实现 wiki chunk × 1.3 加权；触发条件双重校验（结果集含 wiki chunk + KB 开 wiki_enabled）。
- **检索 API 加 KB 类型校验**：纯 wiki KB 调 `knowledge_search` 时返回 400 + 提示"此 KB 未启用向量检索，请用 wiki_search"；纯 RAG KB 调 `wiki_search` 时返回 400 + 提示"此 KB 未启用 wiki 摄入"。
- **失去的能力**：
  - 跨模式联合排序（用户不能在一个 list 里同时看到 RAG 和 Wiki 结果）
  - 意图分类自动路由（参 [ADR-0006](./0006-agent-runtime-byok.md) 弃用章节）
  - 用户 query 级别切模式（被 KB 级别配置替代）

## Open Questions（留给未来 grilling）

- **Open Question A（boost factor 调参）**：✅ **已决策（2026-07-10）**——MVP 硬编码 1.3，**不做 admin 配置项**。理由：YAGNI，MVP 阶段没真实流量做 A/B 也是空谈；暴露配置项会给用户增加认知负担（"这个 1.3 是啥？我该填多少？"）；等 P5 有真实流量需要调参时再加配置项不迟。
- **Open Question B（wiki chunk 切块策略）**：✅ **已决策（2026-07-09）**——wiki 正文切块**复用文档同款策略**（CJK 300 词 / 50 词 overlap）。理由：MVP 简单优先，复用现有 chunking 服务避免多一套逻辑；markdown-aware 切块（按 `##` 标题分块保留结构）留作 P2 优化。
- **Open Question C（wiki_search 中英跨语）**：`~*` 对中文是字节级子串匹配，用户搜"苹果公司"能命中"苹果公司总部"但不能命中"Apple Inc."（除非显式写正则 `苹果公司|Apple Inc.`）。是否需要补充？候选：① MVP 不补（`~*` 已够用）；② P2 加 wiki_pages 的 `aliases` 字段（LLM 抽取时生成中英别名，wiki_search 同时匹配 title/slug/aliases）；③ P3 加 wiki chunk 向量检索作为补充（混合路径 A 和路径 B）。推荐 ① + ②。
- **Open Question D（graph_enabled 何时启用）**：本 ADR 只定义开关字段，graph 抽取的具体行为（实体关系图、图谱可视化）留给 P5+ 单独 ADR。

## 参考实现

参考系统（Go 项目，已实现此模式）：

- `internal/application/repository/wiki_page.go:975` —— wiki_search 的字段权重 SQL
- `chat_pipeline/wiki_boost.go:15` —— `wikiBoostFactor = 1.3` 硬编码
- `internal/types/indexing_strategy.go` —— IndexingStrategy 四开关定义
- `internal/application/service/agent_service.go:411,458,735` —— wiki-qa / hybrid-rag-wiki Agent 预设 + KB 类型推断辅助逻辑

llm_wiki3.0 用 FastAPI + SQLAlchemy：

- **wiki_search 端点**：`GET /api/v1/kb/{kb_id}/wiki/search?q=...&limit=10`，SQLAlchemy `text()` 原生 SQL（保留 `~*` + 字段权重 CASE 表达式），参数化防 SQL 注入。
- **wiki_boost plugin**：Python 函数注册到 `CHUNK_RERANK` 事件钩子（FastAPI 启动时 `register_plugin('chunk_rerank', wiki_boost_handler)`）。
- **IndexingStrategy**：`knowledge_bases` ORM 模型加 4 个 Boolean 字段；KB 创建时序列化为 JSON 返回给前端。
- **chunk_type**：`content_chunks` ORM 模型加 `chunk_type` String 字段 + CHECK 约束；`wiki_page_id` 可空外键。
