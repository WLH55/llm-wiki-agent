# PRD v4.2：自部署 Web 知识库服务（Wiki/RAG 双路径 + 两层 RBAC）

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
- **实体即页面**：实体不是字符串标签，而是 `wiki_pages` 中 `page_type=entity` 的行，可与任意页面（概念 / 综述 / 日志）通过 markdown `[[xxx]]` wikilink 建立双向链接图边（无类型有向）。
- **KB 级可配置**：每个知识库创建时选定分块策略（默认 CJK 300 词；父子分块作为高级可选）、嵌入模型、向量库类型（pgvector 默认，Milvus/Qdrant 可插拔）。
- **多源挂载**：一个 KB 可同时挂 manual / RSS / Yuque / Feishu 多个源，所有 chunks 共享同一 `kb_id`。
- **两层 RBAC**：tenant（自家）+ organization（共享）+ kb_shares 显式共享；fall-through 三步短路合并，自有 KB 全权（详见 [ADR-0002](mydocs/context/docs/adr/0002-tenant-org-rbac.md)）。
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
10. 作为**知识工作者**，我希望 wiki 页面有 7 种明确类型——自动生成 5 种（`summary` 文档摘要 / `entity` 实体 / `concept` 概念 / `index` 系统索引 / `log` 系统日志）+ Agent 手建 2 种（`synthesis` 综合分析 / `comparison` 对比）——以便不同生成路径产出的页面在 schema 层就有清晰区分，且 `index`/`log` 系统页排除在用户目录之外。
11. 作为**知识工作者**，我希望页面之间用 markdown `[[xxx]]` wikilink 自动建立双向链接（无类型有向边，存在 `in_links`/`out_links` 数组），并辅以 `folder_id`+`parent_slug` 目录树归档和 `source_refs`+`chunk_refs` 原文溯源三套边并存，以便图谱可视化/目录树/原文回看各自有清晰语义，避免类型化边被 LLM 抽成"垃圾桶"（详见 [ADR-0003](mydocs/context/docs/adr/0003-three-edge-model.md)）。
12. 作为**Wiki 编辑者**，我希望手动编辑 wiki 页面时使用 last-write-wins + 乐观锁（`version` 字段），以便多人并发编辑不会互相覆盖且无需复杂合并。
13. 作为**Wiki 编辑者**，我希望在编辑冲突时 UI 给出明确提示（"此页面已被他人更新，请刷新"），以便我知道何时需要重新基于最新版本改。
14. 作为**Wiki 编辑者**，我希望 wiki 页面支持目录树（`wiki_folders`）、`wiki_path`、`depth`、`sort_order`，以便组织大型知识库的导航结构。
15. 作为**Wiki 编辑者**，我希望能把整个 wiki 类型 KB 一键导出为 **MD 导出包**（zip：markdown 文件按 `wiki_path` 目录结构组织 + 每文件头部 YAML frontmatter 含 `page_type` / `slug` / `chunk_refs` / `folder_path` / `version`，保留 `[[xxx]]` 双向链接），以便离线阅读或迁移到其他 Wiki 系统（Obsidian / Logseq 等）。RAG 类型 KB 不支持整库导出（无 wiki 页面），只支持原始文档下载。
16. 作为**Wiki 编辑者**，我希望能导出单个 wiki 页面为 MD 文件，以便快速分享给外部协作者。
17. 作为**MCP 工具使用者**，我希望外部 AI 应用（Claude Desktop 通过 mcp-remote 桥接、Cursor、其他 Web 应用）通过 **HTTP MCP 协议**调用 8 个工具（`list_kbs` / `use_kb` / `list_pages` / `search` / `read` / `related` / `chat` / `update`）读写我的知识库，以便 MCP 工具能进行格式化生成 wiki 页（详见 [ADR-0004](mydocs/context/docs/adr/0004-http-mcp-server.md)）。
18. 作为**MCP 工具使用者**，我希望 MCP 写入 wiki 页面（`update` 工具）时带上溯源引用（`chunk_refs` 指向原始 chunks），以便 MCP 沉淀的内容不丢失证据链；当 LLM 自动生成纯综述性内容确实没有明确原文 chunk 可引时，允许 `chunk_refs: []` 但记录到 `process_log` 标记"无溯源"以便治理（详见 ADR-0004 Open Question C）。
19. 作为**组织创建者**，我希望创建一个 organization（共享空间）并邀请成员加入（admin / editor / viewer 三种角色），以便把来自不同 tenant 的 KB 集中到一个共享容器里给团队用。
20. 作为**KB 所有者**，我希望把自家 tenant 里的某个 KB 显式共享给某个 organization（指定 viewer / editor / admin 权限），以便组织成员能按统一权限访问，**而不必逐个用户开 grant**。
21. 作为**组织 admin**，我希望调整某成员的角色（如 editor → viewer）后，该成员对所有共享到此 org 的 KB 的有效权限自动同步收敛，以便人员变动时不必逐条改 KB 共享记录。
22. 作为**所有者**，我希望在任何我自创的 KB 上都自动获得 Admin 权限（无视 organization 视角下显示的共享上限），以便"自有即全权"这一直觉不被 min() 合并破坏；同时希望在「空间视角」下能看到我对每个共享 KB 实际拿到的有效权限（min(share_perm, my_org_role)），以便审计组织级权限配置。
23. 作为**PDF 文档贡献者**，我希望 PDF 解析走 Python worker + Redis 异步队列（pdfium / pdfplumber / unstructured），以便大型 PDF 不阻塞 FastAPI 主进程，且失败可重试、有进度可查。
24. 作为**多模态用户**，我希望图片通过 VLM OCR + Caption 生成可被检索的文本 chunk（`chunk_type=image_ocr` / `image_caption`），以便图片内容也能被搜索命中。
25. 作为**检索用户**，我希望混合搜索（BM25 + 向量 + RRF 融合）能在中英文混排场景下也稳定工作，以便我不用切换搜索引擎。
26. 作为**检索用户**，我希望检索结果带"后融合 Boost"（标题命中、来源加权），以便我看到的不是裸分数排序而是符合直觉的结果。
27. 作为**检索质量关注者**，我希望系统记录 `search_log`（查询、命中、用户点击/采纳），以便后续训练评估集和 Boost 参数。
28. 作为**运维者**，我希望文档处理有 `process_spans` 时间线 UI，以便我看到 PDF 解析、分块、嵌入每一步耗时和失败原因。
29. 作为**运维者**，我希望 schema 指纹折进缓存键，以便我升级 schema 时缓存自动失效、不会读到旧嵌入。
30. 作为**运维者**，我希望向量存储使用 `halfvec` 不带 N 的列声明 + `embedding_dim` 字段 + partial HNSW 索引（按维度分别建索引）+ KB 级模型绑定，以便存储空间节省一半且不同 KB 能用不同维度模型共存（详见 [ADR-0001](mydocs/context/docs/adr/0001-halfvec-multi-dim.md)）。
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
- **Wiki 路径**：LLM 抽取 / 人工编辑 / MCP 沉淀 → `wiki_pages`（PG 全文）→ 双向链接图边（`in_links` / `out_links` 数组，无类型有向，详见 [ADR-0003](mydocs/context/docs/adr/0003-three-edge-model.md)）。
- 两路径共享同一 `kb_id`，检索时可分别 Boost 也可联合排序。
- **Wiki 路径才消耗 LLM token**（实体抽取、综述生成）；RAG 路径在导入时除了嵌入不调 LLM。

### 分块策略

- 默认：CJK 300 词 / 50 词 overlap（中文友好）。
- 父子分块（高级可选）：子块 ~150 词入向量库召回，父块 ~1024 词仅存 DB 用作上下文。
- 其他策略（Tree-sitter 代码语义、固定 token 等）走 KB 级配置 + 适配层。
- KB 创建时选定策略，库里所有文档统一用此策略。
- **每个 KB 都有一个默认配置**（系统提供的预设），用户可在此基础上调整。

### 向量存储

- `content_chunks.embedding` 列声明为 `halfvec`（不带 N，pgvector 允许变长）+ `embedding_dim INT` 记录真实维度；每个维度单独建 partial HNSW 索引 `WHERE embedding_dim = N` 配合表达式 `(embedding::halfvec(N))`。详见 [ADR-0001](mydocs/context/docs/adr/0001-halfvec-multi-dim.md)。
- KB 级模型绑定：`knowledge_bases.embedding_model_id` 记录该 KB 用的模型 + 维度，确保库内维度一致；不同 KB 可用不同模型。
- **不做维度 padding**（反模式）——不同维度向量空间不兼容，零填充后归一化让相似度区分度崩塌。
- 向量库可插拔：默认 pgvector，通过适配层支持 Milvus / Qdrant，应用层不感知后端。

### 多源挂载

- `sources` 表保留 `kb_id` 外键，一个 KB 可挂多个 source（manual / RSS / Yuque / Feishu 等）。
- 每个 source 有自己的同步状态、增量游标。
- 所有 source 的 chunks 共享 `kb_id`，检索时不分源。

### 两层 RBAC + 共享语义

详细决策与合并算法伪代码见 [ADR-0002](mydocs/context/docs/adr/0002-tenant-org-rbac.md)。要点：

- **Tenant（自家）**：每个用户默认拥有一个自家 tenant；KB 创建时挂到 caller 当前 tenant 上下文。tenant 内角色 `TenantRole: owner / admin / contributor / viewer`。
- **Organization（共享容器）**：admin 创建 + 邀请成员（`OrgMemberRole: admin / editor / viewer`），通过 `kb_shares` 挂载来自不同 tenant 的 KB。
- **KBShare 粒度**：`kb_shares(kb_id, org_id, permission)` 三元组，**无 user_id**——共享针对组织而非个人。
- **合并算法（fall-through 三步短路）**：
  1. 自有 KB（`caller.tenantID == kb.tenantID`）→ Admin（无视任何角色）。
  2. 共享 KB：`effective = min(share_perm, my_org_role)`，再过 `applyTenantRoleCap`（只封一种情况：`my_tenant_role == Viewer && effective >= Editor` → 砍到 Viewer）。
  3. 通过 agent 共享间接可见 → Viewer。
  4. 否则 → 403 Forbidden。
- **不在产品里实现 Postgres RLS**：自注册 + 邀请制场景下应用层 RBAC 已够；RLS 留作未来企业版升级路径。

### 页面与图谱模型

详细决策、伪代码、参考实现路径见 [ADR-0003](mydocs/context/docs/adr/0003-three-edge-model.md)。要点：

- **页面类型 7 种**：自动生成 5 种（`summary` / `entity` / `concept` / `index` / `log`）+ Agent 手建 2 种（`synthesis` / `comparison`）；`index`/`log` 是系统页，排除在用户目录之外。
- **链接图边**：从 markdown `[[xxx]]` 正则抽取，双向冗余存 `pages.in_links` / `pages.out_links` 数组，**无类型、无权、有向**。永久放弃类型化边（PRD 原 US 11 的"8 种语义边"已废弃）。
- **目录树边**：`pages.folder_id`（source of truth）+ `pages.parent_slug`（可选语义父）+ `wiki_folders` 邻接表；`category_path`/`depth`/`wiki_path` 是物化路径缓存（每次写重算）；深度上限 3 层。
- **溯源边**：`pages.source_refs`（`<kb_id>|<doc_title>` 文档级）+ `pages.chunk_refs`（chunk UUID 级）。`summary` 页通常 `chunk_refs` 空；`entity`/`concept`/`synthesis`/`comparison` 页带 chunk 级引用。
- **slug 唯一性**：KB 内唯一，跨 KB 不唯一。`index`/`log` 保留给系统页。

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
  embedding       halfvec,        -- 不带 N，pgvector 允许变长；与 embedding_dim 配合做 partial HNSW
  embedding_dim   INT,            -- 真实维度（如 1024 / 3072），与 KB 级模型绑定一致
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

FastAPI 服务在 `/mcp` 端点暴露 **HTTP MCP server**（Streamable HTTP 协议，spec 2025-03-26+）。详见 [ADR-0004](mydocs/context/docs/adr/0004-http-mcp-server.md)。

- 8 个工具：`list_kbs` / `use_kb` / `list_pages` / `search` / `read` / `related` / `chat` / `update`。
- 鉴权：API Key（用户在 Web UI 生成，绑定 user_id + workspace context）；客户端在 `Authorization: Bearer <key>` 里带 key。
- RBAC：调用时按 API Key 绑定的 workspace context 走 [ADR-0002](mydocs/context/docs/adr/0002-tenant-org-rbac.md) 的 fall-through 三步短路。
- 外部接入：Claude Desktop / Cursor 等桌面 IDE 应用通过 mcp-remote 桥接（用户文档需写明配置指南）；其他 Web 应用直接 HTTP 接入。
- `update` 工具写入 wiki 页面时**默认要求**带 `chunk_refs` 溯源；纯综述性内容允许 `chunk_refs: []` 但记录到 `process_log` 标记"无溯源"以便治理（详见 ADR-0004 Open Question C）。

### 多模态

- 图片走 VLM OCR（提取文字 → `chunk_type=image_ocr`）+ Caption（生成描述 → `chunk_type=image_caption`）。
- 两类 chunk 都进向量库参与混合检索。

### 缓存键

- schema 指纹（DDL 哈希 + 嵌入模型版本 + 分块策略版本）折进嵌入缓存键，升级 schema 自动失效。

### IM 通知（Phase 5）

- 单向 webhook 推送（飞书 / 钉钉），不做双向对话。

### Phase 划分（高层）

- **P1**：Docker Compose 起服；KB 创建（含分块/模型/向量库选择）；多源挂载；RAG 默认分块 + 父子分块可选；Wiki 基础表；halfvec 不带 N + partial HNSW 多维度共存（[ADR-0001](mydocs/context/docs/adr/0001-halfvec-multi-dim.md)）；Python worker + Redis 队列做 PDF 解析（替代 Rust sidecar）。
- **P2**：双 AI 通道；AI 对话；7 种页面类型 + 实体/概念 LLM 抽取；三套边模型（链接图 / 目录树 / 溯源）；Wiki 手动编辑 + last-write-wins；MCP 工具手动沉淀。
- **P3**：两层 RBAC（tenant + organization + kb_shares + fall-through 合并）；Wiki MD 导出（单页 + 整库）；MCP 工具集；意图分类零 LLM；后融合 Boost；search_log；process_spans UI。
- **P4**：向量库可插拔（Milvus / Qdrant）；本地目录监控 + RSS 数据源；Tree-sitter 代码分块；VLM OCR + Caption。
- **P5**：知识编译（可选）；Cross-encoder 重排序；评估体系；完整后融合 Boost；IM 通知；语雀数据源。
- **P6**：飞书文档同步；Notion 连接；跨会话记忆（Agent Memory）。

## Testing Decisions

### 总原则

- 只测外部行为（API 契约、用户可见流程），不测内部实现细节（私有函数、内部辅助）。
- 优先用最高层 seams：API route level（Next.js Route Handlers）+ DB integration。
- 一个 feature 只在一层测，不重复。

### Seams 优先级

1. **FastAPI 端点层（首选）**：所有 CRUD、检索、对话、MCP 适配都通过 FastAPI 的 `/api/*` 端点暴露（Next.js 仅做 BFF 转发，不承担业务逻辑），测试直接打 HTTP。
2. **DB 集成层**：用于验证 schema、迁移、RBAC fall-through 合并算法、向量检索 SQL、双向链接 closure 等数据层行为。用 testcontainers 起一次性 Postgres + pgvector。
3. **E2E 冒烟（最少）**：仅覆盖 docker-compose up → 导入文档 → 检索命中 这一条主路径。

### 关键场景的测试归属

- **两层 RBAC fall-through**：DB 集成测试，覆盖四个分支（① 自有 KB → Admin；② 共享 KB → `min(share_perm, my_org_role)` 走 applyTenantRoleCap；③ agent 间接 → Viewer；④ 未共享 → 403）+ applyTenantRoleCap 五种 (effective, tenant_role) 组合。详见 [ADR-0002](mydocs/context/docs/adr/0002-tenant-org-rbac.md)。
- **last-write-wins**：API 测试，并发两个 PUT 同一 page_id + version，断言一个 200 一个 409。
- **halfvec 多维度共存**：DB 测试，见 [ADR-0001](mydocs/context/docs/adr/0001-halfvec-multi-dim.md)。在同一 KB 写入 1024 维 chunk、另一 KB 写入 3072 维 chunk，断言：① 各自的 partial HNSW 索引被命中（`EXPLAIN` 无全表扫）；② 查询时 `embedding::halfvec(N)` cast 不带维度会静默退化全表扫（验证应用层 SQL 必须 cast）；③ 不同维度间不做比较（跨 KB 检索不返回相似度）。
- **三套边模型（链接图 / 目录树 / 溯源）**：见 [ADR-0003](mydocs/context/docs/adr/0003-three-edge-model.md)。API 测试覆盖：① 链接图边——POST 含 `[[B]]` wikilink 的 A 页面，断言 A.out_links 和 B.in_links 双向更新；② 目录树边——POST 一个 folder_id 链 3 层深的页面，断言 category_path/depth/wiki_path 缓存正确物化，且第 4 层被 400 拒绝；③ 溯源边——POST entity 页带 chunk_refs，删除被引用的原文档后断言对应 chunk_ref 被清掉。
- **页面类型**：API 测试，POST 7 种 page_type 各一条，断言 index/log 被 `wikiIndexContentPageTypes` 排除在用户目录之外；POST 用户尝试创建 slug=`index` 的页面应被 400 拒绝（系统页保留）。
- **多源挂载**：API 测试，给一个 KB 挂 manual + RSS 两个 source，导入后断言 chunks 都在同一 kb_id 下。
- **向量库可插拔**：适配层接口测试，给定一个 IVectorStore mock，断言应用层不感知后端切换。
- **MCP 溯源**：MCP `update` 工具测试，调用 update 带 `chunk_refs: []` 应被接受，且 `process_log` 生成一条"无溯源"标记；调用 update 带 `chunk_refs: ["<chunk_uuid>"]` 应被接受，且 `wiki_pages.chunk_refs` 写入对应值（详见 [ADR-0004](mydocs/context/docs/adr/0004-http-mcp-server.md)）。
- **PDF 解析异步队列**：契约测试，提交一个 PDF 文件触发异步任务，断言 Redis 队列收到任务 + Python worker 消费后返回的 JSON 结构（含 chunk 列表 / process_spans 时间线 / 失败重试）。
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
- 参考：WeKnora（Wiki/RAG 双路径、实体即页面、halfvec 维度、向量库可插拔）；GBrain（图谱边的语义化、schema 继承——后者暂缓）。本 PRD v4.2 的两层 RBAC（tenant + organization + kb_shares）参考了 WeKnora 早期实现，落地方案见 [ADR-0002](mydocs/context/docs/adr/0002-tenant-org-rbac.md)。
- 一旦 `gh` CLI 可用，应将本 PRD 通过 `gh issue create --label ready-for-agent` 发布到 `WLH55/llm-wiki-agent` 仓库。
- v4.2 是相对 v4.1 的重大转向（弃用桌面客户端，全面 Web 化）；后续若再次大改，建议先做 ADR 而非直接重写 PRD。
