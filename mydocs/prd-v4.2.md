# PRD v4.2：自部署 Web 知识库服务（Wiki/RAG 双路径 + 三档 RBAC）

> 来源：`/grill-with-docs` → `/to-prd` 流水线。基于 `prototype/prd-v4.0.html`（v4.2 内容）与 WeKnora/GBrain 参考设计综合得出。
> Triage label: `ready-for-agent`

---

## Problem Statement

团队需要一个**可自部署的 Web 知识库服务**，把"原始文档检索"和"AI 沉淀的结构化知识"两条路径都做好：

- 用户既有大量原始文档（PDF / Word / Markdown / RSS / Yuque / Feishu）需要 **RAG 检索**；
- 用户在与 AI 对话、人工编辑过程中产生的 **结构化沉淀**（实体卡、概念页、综述、AI 写作产物）需要 **Wiki 化管理**（双向链接、版本、目录树、可导出）；
- 既要支持个人单机使用，又要支持团队多人共享同一份数据，且权限要细粒度可控；
- 现有的桌面客户端架构（PGLite + Tauri 双引擎）让数据分布在每个用户的本地，**团队共享、备份、迁移都很别扭**，维护成本也高。

## Solution

把产品定位从"Navicat 风格的桌面客户端"重新调整为**"一个 docker-compose up 即可让团队拥有自己的 Web 知识库服务"**：

- **单一 Web 部署模型**：弃用 PGLite/Tauri，统一为 Docker（Postgres + pgvector + MinIO + Next.js + Rust sidecar）。个人也跑同一个镜像，团队再多人共用一份。
- **Wiki / RAG 双路径分离**（WeKnora 模式）：
  - **RAG 路径**：原始文档 → 多种分块策略 → pgvector 向量检索 + PG 全文双路混合；
  - **Wiki 路径**：LLM 抽取实体 / 概念 / 综述 → `wiki_pages` 表（PG 全文 + 双向链接），可手动编辑、版本化、整库导出 MD。
- **实体即页面**：实体不是字符串标签，而是 `wiki_pages` 中 `page_type=entity` 的行，可与任意页面（概念 / 综述 / 日志）建立双向语义边。
- **KB 级可配置**：每个知识库创建时选定分块策略（默认 CJK 300 词；父子分块作为高级可选）、嵌入模型、向量库类型（pgvector 默认，Milvus/Qdrant 可插拔）。
- **多源挂载**：一个 KB 可同时挂 manual / RSS / Yuque / Feishu 多个源，所有 chunks 共享同一 `kb_id`。
- **三档 RBAC**：workspace 默认权限 + KB 级 grant + membership 角色，三者取 `min()` 合并。
- **last-write-wins + 乐观锁**：不做 Git 式分支合并，简单可靠；UI 在冲突时给提示。
- **Wiki 类型 KB 整库 MD 导出**：保留可读性，放弃 OKF 互操作格式。

## User Stories

1. 作为**团队管理员**，我希望一份 `docker-compose up` 就能起一个完整的知识库服务（含 Postgres、pgvector、MinIO、Next.js Web、PDF 解析 sidecar），以便 5 分钟内交付给团队。
2. 作为**个人用户**，我希望在本地用同一份 Docker 镜像跑知识库（不强制上云），以便数据完全私有。
3. 作为**知识库创建者**，我希望在创建 KB 时能选择分块策略（默认 / 父子分块 / 其他高级策略），以便不同语料用不同策略。
4. 作为**知识库创建者**，我希望在创建 KB 时能选择嵌入模型（如 bge-m3、text-embedding-3-large 等），以便 KB 内所有 chunks 维度一致。
5. 作为**知识库创建者**，我希望在创建 KB 时能选择向量库后端（pgvector 默认 / Milvus / Qdrant），以便后期切换不必重写应用层。
6. 作为**文档贡献者**，我希望在一个 KB 下同时挂载 manual 上传、RSS 订阅、Yuque 同步、Feishu 同步多个源，以便所有来源的 chunks 共享同一检索入口。
7. 作为**检索用户**，我希望搜索结果同时覆盖 RAG 路径（原始文档切片）和 Wiki 路径（LLM 生成的实体/概念页），以便一次搜索拿到原始证据 + 结构化总结。
8. 作为**检索用户**，我希望在阅读 Wiki 页面时，每段文字能溯源到具体的原始 chunk（`chunk_refs`），以便我验证 AI 生成内容是否忠于原文。
9. 作为**AI 对话用户**，我希望对话回答附带引用，引用回链到 `content_chunks` 的具体 chunk，以便我快速跳转原始上下文。
10. 作为**知识工作者**，我希望实体不是字符串标签而是一个独立页面（`page_type=entity`），以便实体本身可被双向链接、可被综述引用、可独立检索。
11. 作为**知识工作者**，我希望实体页之间能存在 8 种语义边（如 `related_to` / `sub_of` / `instance_of` / `derived_from` 等），以便表达比"只是关联"更丰富的关系。
12. 作为**Wiki 编辑者**，我希望手动编辑 wiki 页面时使用 last-write-wins + 乐观锁（`version` 字段），以便多人并发编辑不会互相覆盖且无需复杂合并。
13. 作为**Wiki 编辑者**，我希望在编辑冲突时 UI 给出明确提示（"此页面已被他人更新，请刷新"），以便我知道何时需要重新基于最新版本改。
14. 作为**Wiki 编辑者**，我希望 wiki 页面支持目录树（`wiki_folders`）、`wiki_path`、`depth`、`sort_order`，以便组织大型知识库的导航结构。
15. 作为**Wiki 编辑者**，我希望能把整个 wiki 类型 KB 一键导出为 MD 文件包（保留目录结构与双向链接），以便离线阅读或迁移到其他 Wiki 系统。
16. 作为**Wiki 编辑者**，我希望能导出单个 wiki 页面为 MD 文件，以便快速分享给外部协作者。
17. 作为**MCP 工具使用者**，我希望通过 MCP 工具（`list_kbs` / `use_kb` / `list_pages` / `search` / `read` / `related` / `chat` / `update`）让外部 AI 应用（如 Claude Desktop）读写我的知识库，以便 MCP 工具能进行格式化生成 wiki 页。
18. 作为**MCP 工具使用者**，我希望 MCP 写入 wiki 页面时也带上溯源引用（指向原始 chunks），以便 MCP 沉淀的内容不丢失证据链。
19. 作为**workspace 管理员**，我希望设置 workspace 默认权限（如"全员只读"），以便新成员无需单独配置就受约束。
20. 作为**KB 所有者**，我希望对特定 KB 单独 grant 给某用户/组（如"小明可写"），以便个别 KB 突破默认权限。
21. 作为**workspace 管理员**，我希望 membership 角色层级（owner / writer / reader）作为兜底约束，以便组织架构变化时权限不爆炸。
22. 作为**workspace 管理员**，我希望三档权限（workspace / kb_grant / membership）按 `min()` 合并生效，以便权限不会因某一档放宽而泄漏。
23. 作为**PDF 文档贡献者**，我希望 PDF 解析走 Rust sidecar（pdfium），以便大型 PDF 不阻塞 Node 主进程。
24. 作为**多模态用户**，我希望图片通过 VLM OCR + Caption 生成可被检索的文本 chunk（`chunk_type=image_ocr` / `image_caption`），以便图片内容也能被搜索命中。
25. 作为**检索用户**，我希望混合搜索（BM25 + 向量 + RRF 融合）能在中英文混排场景下也稳定工作，以便我不用切换搜索引擎。
26. 作为**检索用户**，我希望检索结果带"后融合 Boost"（标题命中、来源加权），以便我看到的不是裸分数排序而是符合直觉的结果。
27. 作为**检索质量关注者**，我希望系统记录 `search_log`（查询、命中、用户点击/采纳），以便后续训练评估集和 Boost 参数。
28. 作为**运维者**，我希望文档处理有 `process_spans` 时间线 UI，以便我看到 PDF 解析、分块、嵌入每一步耗时和失败原因。
29. 作为**运维者**，我希望 schema 指纹折进缓存键，以便我升级 schema 时缓存自动失效、不会读到旧嵌入。
30. 作为**运维者**，我希望向量存储使用 `halfvec(3072)` 半精度 + 维度 padding + KB 级模型绑定，以便存储空间节省一半且多模型共存可行。
31. 作为**运维者**，我希望"上下文检索"在嵌入时包裹文档上下文（一次到位），以便后续不必全量重嵌入。
32. 作为**内容治理者**，我希望导入时跑内容验证管线（`content_hash` 幂等 + 垃圾/隐私检测），以便避免重复入库和敏感数据泄漏。
33. 作为**团队管理员**，我希望 Phase 5 支持 IM 通知（飞书 / 钉钉 webhook），以便知识库更新能推到群。
34. 作为**团队管理员**，我希望 Phase 5+ 支持语雀数据源连接，以便团队既有的语雀知识能增量同步进来。
35. 作为**AI 应用开发者**，我希望意图分类走零 LLM 路径（关键词/规则），以便分类延迟低、可解释。
36. 作为**评估者**，我希望 Phase 5 引入 Cross-encoder 重排序 + 评估体系，以便 P@5 持续可量化提升。

## Implementation Decisions

### 整体架构

- **单一部署模型**：Docker Compose 一键起服，包含 `postgres`（含 pgvector 扩展）、`minio`（对象存储）、`nextjs`（Web 主应用）、`rust-sidecar`（PDF 解析）。不再有 PGLite / Tauri / 双引擎分支。
- **个人 vs 团队**：用同一镜像、同一 schema；个人即"团队 = 1 人"的特例，不再有"个人模式/团队模式"切换。
- **可迁移性**：放弃桌面客户端的"KB 可移植包"概念；数据存数据库即可备份（pg_dump），不另设计 OKF 互操作格式。

### 双路径分离（核心架构决策）

- **RAG 路径**：原始文档 → 解析 → 分块 → `content_chunks`（带 embedding）→ pgvector 检索。
- **Wiki 路径**：LLM 抽取 / 人工编辑 / MCP 沉淀 → `wiki_pages`（PG 全文）→ 双向链接（`links` 表）。
- 两路径共享同一 `kb_id`，检索时可分别 Boost 也可联合排序。
- **Wiki 路径才消耗 LLM token**（实体抽取、综述生成）；RAG 路径在导入时除了嵌入不调 LLM。

### 分块策略

- 默认：CJK 300 词 / 50 词 overlap（中文友好）。
- 父子分块（高级可选）：子块 ~150 词入向量库召回，父块 ~1024 词仅存 DB 用作上下文。
- 其他策略（Tree-sitter 代码语义、固定 token 等）走 KB 级配置 + 适配层。
- KB 创建时选定策略，库里所有文档统一用此策略。
- **每个 KB 都有一个默认配置**（系统提供的预设），用户可在此基础上调整。

### 实体即页面

- `wiki_pages.page_type ∈ {entity, concept, summary, synthesis, index, log}`。
- 实体不再是字符串标签或独立表，而是 `page_type=entity` 的 wiki_pages 行。
- 实体间关系存在 `links` 表（`from_page_id` / `to_page_id` / `link_type`），8 种 link_type 覆盖常见语义关系。
- `in_links` / `out_links` 作为 JSONB 冗余加速读路径。

### 向量存储

- `content_chunks.embedding` 使用 `halfvec(3072)`（半精度）。
- 维度 padding：每个 chunk 同时记录 `embedding_dim`（真实维度），不足 3072 的零填充。
- KB 级模型绑定：`knowledge_bases.embedding_model_id` 记录该 KB 用的模型，确保库内维度一致。
- 向量库可插拔：默认 pgvector，通过适配层支持 Milvus / Qdrant，应用层不感知后端。

### 多源挂载

- `sources` 表保留 `kb_id` 外键，一个 KB 可挂多个 source（manual / RSS / Yuque / Feishu 等）。
- 每个 source 有自己的同步状态、增量游标。
- 所有 source 的 chunks 共享 `kb_id`，检索时不分源。

### 三档 RBAC

- **L1 workspace**：`workspaces.default_permission` 设 workspace 默认权限（如 `read` / `none`）。
- **L2 kb_grant**：`kb_grants` 表对特定 KB 单独 grant 给 user/group。
- **L3 membership**：`memberships.role` 设 owner / writer / reader。
- **合并规则**：三者取 `min()`（最严格档位生效）。

### 并发控制（Wiki 编辑）

- `wiki_pages.version` 字段做乐观锁。
- 写入时 `WHERE id = ? AND version = ?`，失败则返回 409，UI 提示"页面已被他人更新，请刷新"。
- 不做 Git 式分支合并，不做三路 merge。

### 数据模型关键 DDL（节选）

```sql
CREATE TABLE content_chunks (
  id              SERIAL PRIMARY KEY,
  page_id         INT REFERENCES pages(id) ON DELETE CASCADE,
  kb_id           INT REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  chunk_index     INT,
  chunk_type      TEXT NOT NULL,  -- text/parent_text/image_ocr/image_caption/summary/faq/table_*
  parent_chunk_id INT REFERENCES content_chunks(id) ON DELETE CASCADE,
  body            TEXT,
  embedding       halfvec(3072),
  embedding_dim   INT,
  search_vector   TSVECTOR,
  metadata        JSONB,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE wiki_pages (
  id              SERIAL PRIMARY KEY,
  kb_id           INT REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  slug            TEXT NOT NULL,
  title           TEXT,
  page_type       TEXT NOT NULL,  -- entity/concept/summary/synthesis/index/log
  content         TEXT,
  summary         TEXT,
  status          TEXT DEFAULT 'draft',
  folder_id       INT,
  category_path   JSONB,
  wiki_path       TEXT,
  depth           INT,
  sort_order      INT DEFAULT 0,
  source_refs     JSONB,
  chunk_refs      JSONB,
  in_links        JSONB,
  out_links       JSONB,
  version         INT DEFAULT 1,
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ,
  deleted_at      TIMESTAMPTZ,
  UNIQUE(kb_id, slug)
);

CREATE TABLE links (
  id              SERIAL PRIMARY KEY,
  kb_id           INT REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  from_page_id    INT REFERENCES wiki_pages(id) ON DELETE CASCADE,
  to_page_id      INT REFERENCES wiki_pages(id) ON DELETE CASCADE,
  link_type       TEXT NOT NULL,
  link_source     TEXT NOT NULL,
  weight          REAL DEFAULT 1.0,
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(from_page_id, to_page_id, link_type)
);
```

### MCP 工具集（Phase 3）

8 个工具：`list_kbs` / `use_kb` / `list_pages` / `search` / `read` / `related` / `chat` / `update`。`update` 写入 wiki 页面时必须带 `chunk_refs` 溯源。

### 多模态

- 图片走 VLM OCR（提取文字 → `chunk_type=image_ocr`）+ Caption（生成描述 → `chunk_type=image_caption`）。
- 两类 chunk 都进向量库参与混合检索。

### 缓存键

- schema 指纹（DDL 哈希 + 嵌入模型版本 + 分块策略版本）折进嵌入缓存键，升级 schema 自动失效。

### IM 通知（Phase 5）

- 单向 webhook 推送（飞书 / 钉钉），不做双向对话。

### Phase 划分（高层）

- **P1**：Docker Compose 起服；KB 创建（含分块/模型/向量库选择）；多源挂载；RAG 默认分块 + 父子分块可选；Wiki 基础表；halfvec(3072) + 维度 padding；Rust sidecar PDF 解析。
- **P2**：双 AI 通道；AI 对话；实体即页面 LLM 抽取；溯源引用；8 种语义边；Wiki 手动编辑 + last-write-wins；MCP 工具手动沉淀。
- **P3**：三档 RBAC；Wiki MD 导出（单页 + 整库）；MCP 工具集；意图分类零 LLM；后融合 Boost；search_log；process_spans UI。
- **P4**：向量库可插拔（Milvus / Qdrant）；本地目录监控 + RSS 数据源；Tree-sitter 代码分块；VLM OCR + Caption。
- **P5**：知识编译（可选）；Cross-encoder 重排序；评估体系；完整后融合 Boost；IM 通知；语雀数据源。
- **P6**：飞书文档同步；Notion 连接；跨会话记忆（Agent Memory）。

## Testing Decisions

### 总原则

- 只测外部行为（API 契约、用户可见流程），不测内部实现细节（私有函数、内部辅助）。
- 优先用最高层 seams：API route level（Next.js Route Handlers）+ DB integration。
- 一个 feature 只在一层测，不重复。

### Seams 优先级

1. **API Route 层（首选）**：所有 CRUD、检索、对话、MCP 适配都通过 `/api/*` Route Handlers 暴露，测试直接打 HTTP。
2. **DB 集成层**：用于验证 schema、迁移、RBAC min() 合并、向量检索 SQL、双向链接 closure 等数据层行为。用 testcontainers 起一次性 Postgres + pgvector。
3. **E2E 冒烟（最少）**：仅覆盖 docker-compose up → 导入文档 → 检索命中 这一条主路径。

### 关键场景的测试归属

- **三档 RBAC min()**：DB 集成测试，对每个 (workspace_default, kb_grant, membership) 三元组断言有效权限。
- **last-write-wins**：API 测试，并发两个 PUT 同一 page_id + version，断言一个 200 一个 409。
- **halfvec padding**：DB 测试，写入不同 embedding_dim 的 chunk，断言检索能跨维度排序。
- **实体即页面**：API 测试，POST 一个 `page_type=entity`，再 POST 一个引用它的概念页，断言 `in_links` / `out_links` 双向更新。
- **多源挂载**：API 测试，给一个 KB 挂 manual + RSS 两个 source，导入后断言 chunks 都在同一 kb_id 下。
- **向量库可插拔**：适配层接口测试，给定一个 IVectorStore mock，断言应用层不感知后端切换。
- **MCP 溯源**：MCP `update` 工具测试，调用 update 不带 `chunk_refs` 应被拒绝。
- **PDF 解析 sidecar**：契约测试，给定固定 PDF 文件，断言 Rust sidecar 返回的 JSON 结构。
- **search_log**：DB 集成测试，断言每次 search 都生成一条 log，含查询、命中 top-k、用户 id。
- **Docker 部署**：CI 中跑一次 `docker-compose up`，等待健康检查，跑一遍 E2E 冒烟。

### Prior art

- 现有项目暂无测试代码（仍处原型阶段），新仓库从 Vitest（前端 + API）+ testcontainers（DB 集成）+ Playwright（E2E）三件套起步。

## Out of Scope

- **OKF 互操作格式**：不再设计，Wiki 仅支持 MD 导出（单页 + 整库）。
- **Git 式分支合并 / 三路 merge**：Wiki 编辑走 last-write-wins，不做合并。
- **跨会话 Agent Memory**：留给未来 Phase 6+。
- **桌面客户端 / Tauri 打包 / PGLite 单机模式**：v4.2 全面 Web 化，不再维护。
- **KB 可移植包 / 跨实例迁移**：用 pg_dump 备份即可，不另设计便携格式。
- **双向 IM 对话**：IM 仅做单向 webhook 推送通知，不做双向对话机器人。
- **嵌入式 RBAC 编辑器 UI**：Phase 3 先用配置文件 + 简单 UI，复杂可视化编辑留给后续。
- **多语言全文搜索的高级分词**：Phase 1 用 PG 默认分词 + zhparser 扩展即可，不引入外部 ES。

## Further Notes

- 本 PRD 由 `/grill-with-docs` 流程产出，22 个关键决策均已与用户对齐（详见 `prototype/prd-v4.0.html` 中 v4.2 changelog callout）。
- 参考：WeKnora（Wiki/RAG 双路径、实体即页面、halfvec 维度、向量库可插拔、三档权限模型）；GBrain（图谱边的语义化、schema 继承——后者暂缓）。
- 一旦 `gh` CLI 可用，应将本 PRD 通过 `gh issue create --label ready-for-agent` 发布到 `WLH55/llm-wiki-agent` 仓库。
- v4.2 是相对 v4.1 的重大转向（弃用桌面客户端，全面 Web 化）；后续若再次大改，建议先做 ADR 而非直接重写 PRD。
