# SDD Spec: MVP P1 Batch 1 - RAG Foundation

## RIPER 状态

- **phase**: PLAN
- **approval status**: AWAITING_PLAN_APPROVAL
- **spec path**: `mydocs/specs/2026-07-10_00-11_mvp-p1-batch1-rag-foundation.md`
- **active project**: llm_wiki3.0（单项目）
- **change scope**: local

---

## §0 Open Questions

> ✅ 全部已决策（2026-07-10），进入 Plan 阶段。

- [x] **Q1：嵌入模型调用方式？** → **B（API 调用）**
  - 第一批用 API 调用嵌入模型（env var `EMBEDDING_API_KEY` + `EMBEDDING_API_BASE` + `EMBEDDING_MODEL`）
  - 推荐 provider：SiliconFlow 托管的 bge-m3（`https://api.siliconflow.cn/v1`，与本地 bge-m3 维度一致 1024，未来切本地零成本）
  - 不装 PyTorch / sentence-transformers，减少 worker 容器体积
  - 本地部署模式留给 P2（用 env var `EMBEDDING_PROVIDER=local` 切换）

- [x] **Q2：中文分词是否必须装 zhparser？** → **A（MVP 就装）**
  - 自定义 Postgres Dockerfile：基于 `postgres:16` + 编译安装 `pgvector` + `zhparser`
  - `search_vector` 列用 `to_tsvector('chinese_zh', content)` 维护

- [x] **Q3：MinIO 是否必须 MVP？** → **A（MVP 就用）**
  - Docker Compose 加一个 MinIO 容器（零成本）
  - 原始文档存 MinIO，避免后期从本地文件系统迁移

- [x] **Q4：第一批前端范围？** → **B（最小前端）**
  - 只做 1 个搜索页：query 输入 + top-K chunks 结果列表
  - KB 创建 / 文档上传用 curl 或 Swagger UI 测（FastAPI 自带 `/docs`）

- [x] **Q5：测试策略？** → **B（关键路径测试）**
  - 覆盖：halfvec 多维度 + EXPLAIN 索引命中 / RRF 融合 / JWT 鉴权 / 文档上传闭环
  - 不追求 80% 覆盖率，聚焦容易踩坑的点

- [x] **Q6：LLM chat 系统兜底 key？** → **延后（第一批不需要）**
  - 第一批不做 chat / 抽取，不需要 LLM key
  - 第三批实现 chat 时再配置 `LLM_API_KEY` + `LLM_PROVIDER`

---

## §1 Requirements (Context)

### Goal

实现 MVP（P1）**第一批**：基础设施 + KB 创建 + 文档上传 + RAG 检索最小闭环，**验证核心技术栈**（pgvector halfvec 多维度 + BM25 + RRF 融合 + 中文分词 + Docker Compose 一键部署）。

第一批跑通后，用户可以：
1. `docker-compose up` 一键起服
2. 创建一个 KB（默认 bge-m3 + 混合 IndexingStrategy）
3. 上传 PDF/MD/Word 文档（manual source）
4. 文档异步解析 + 分块 + 嵌入
5. 搜索框输入 query → 返回 top-K chunks（向量 + BM25 + RRF 融合）

### In-Scope（第一批必做）

| # | 模块 | 范围 | 关联 ADR |
|---|------|------|---------|
| 1 | **Docker Compose 骨架** | Postgres + pgvector + zhparser + Redis + MinIO + FastAPI + Next.js + Python worker | PRD §Solution |
| 2 | **数据库 schema** | 核心表：`users` / `tenants` / `knowledge_bases` / `sources` / `content_chunks` + IndexingStrategy 四开关 + `chunk_type` 字段 + halfvec 多维度 + partial HNSW 索引 | ADR-0001 / ADR-0009 |
| 3 | **bootstrap owner 鉴权** | env var `BOOTSTRAP_OWNER_EMAIL/PASSWORD` 启动时创建 owner + JWT session（HS256，24h，无 refresh） | ADR-0008 |
| 4 | **KB 创建 API** | `POST /api/v1/kb` 创建 KB，默认 bge-m3 + 混合 IndexingStrategy；绑定嵌入模型 + 维度 | ADR-0001 / ADR-0009 |
| 5 | **文档上传 API** | `POST /api/v1/kb/{id}/documents` 上传文档 → MinIO 存原始文件 → Redis 队列异步处理；Python worker 消费：解析（pdfium/pdfplumber/unstructured）+ 分块（CJK 300 词 / 50 词 overlap）+ 嵌入 + 写 `content_chunks` | ADR-0007（manual adapter） |
| 6 | **路径 B 检索 API** | `GET /api/v1/kb/{id}/search?q=...&mode=rag` 返回 top-K chunks；pgvector 向量检索 + PG 全文 BM25（zhparser 中文分词）+ Python RRF 融合；**wiki chunk boost 1.3 暂不实现**（第一批无 wiki chunk） | ADR-0009 |
| 7 | **最小前端** | 1 个搜索页：query 输入框 + top-K chunks 结果列表（title / score / snippet / 来源文档） | Q4 推荐方案 B |

### Out-of-Scope（留给后续批次/P2+）

- **路径 A wiki_search**（ADR-0009）：第二批
- **LLM 抽取 wiki 页面**（实体/概念/综述）：第二批
- **wiki chunk boost 1.3**（CHUNK_RERANK plugin）：第二批（wiki 抽取后才有意义）
- **LLM chat + SSE 流式**：第三批
- **wiki 手动编辑**（last-write-wins）：第三批
- **多 user / 邀请制 / workspace context 切换**：P2（ADR-0005）
- **BYOK**（用户自填 key）：P2（ADR-0006）；MVP 用系统兜底 key
- **两层 RBAC**（tenant + organization + kb_shares）：P2（ADR-0002）；MVP 只 bootstrap owner 一人
- **HTTP MCP server**：P3（ADR-0004）
- **多源挂载**（RSS / Yuque / Feishu）：P3+（ADR-0007）；MVP 只 manual
- **MD 导出包**：P3
- **目录树**（folder_id + 物化路径缓存）：P2（ADR-0003）
- **意图分类**：已弃用（ADR-0009）
- **多模态**（VLM OCR / Caption）：P4

### 验收标准（第一批）

1. `docker-compose up` 一键起服，所有容器健康
2. 用 bootstrap owner 登录拿 JWT
3. 创建一个 KB（API 返回 KB id + 默认配置）
4. 上传一个 PDF + 一个 MD（API 返回 doc_id，异步处理）
5. 等待 worker 处理完成（轮询文档状态）
6. 搜索框输入 query → 返回 top-10 chunks（向量+BM25+RRF 融合）
7. 验证：
   - 中文 query 能召回（如"知识库"命中含"知识库"的 chunk）
   - 英文 query 能召回
   - 中英混排 query 能召回
   - top-1 结果与 query 语义相关（人工抽检）
8. DB 层验证：halfvec partial HNSW 索引命中（`EXPLAIN` 无全表扫）

---

## §1.1 Context Sources

- **Requirement Source**：
  - `mydocs/prd-v4.2.md`（PRD v4.2，行 250-263 MVP 描述）
  - `mydocs/context/docs/adr/0008-mvp-scope.md`（MVP 范围与砍点）
- **Design Refs**：
  - `mydocs/context/docs/adr/0001-halfvec-multi-dim.md`（halfvec 多维度共存）
  - `mydocs/context/docs/adr/0009-retrieval-architecture.md`（双路径 + IndexingStrategy + boost）
  - `mydocs/context/docs/adr/0007-multi-source-mounting.md`（多源挂载，第一批只做 manual adapter）
  - `mydocs/context/docs/adr/0006-agent-runtime-byok.md`（BYOK，P2 才用，第一批用系统兜底 key）
  - `mydocs/context/docs/adr/0003-three-edge-model.md`（三套边，第一批只做 chunk_refs 溯源边）
  - `mydocs/context/docs/adr/0002-tenant-org-rbac.md`（两层 RBAC，P2 才用，第一批 bootstrap owner）
- **Chat/Business Refs**：
  - grilling 全程对话记录（task #1-#9 完成）
  - 用户最终决策（2026-07-10）：分批实现，第一批聚焦 RAG 基础闭环
- **Extra Context**：
  - `mydocs/context/CONTEXT.md`（术语表）
  - `prototype/`（HTML 原型，参考 UI 布局）

---

## §1.5 Codemap Used

- **Codemap Mode**：N/A
- **Codemap File**：N/A
- **Key Index**：本项目为全新实现，无既有代码索引；Research 阶段基于 PRD/ADR/CONTEXT 文档

---

## §1.6 Context Bundle Snapshot

- **Bundle Level**：N/A
- **Bundle File**：N/A
- **Key Facts**：直接复用 grilling 阶段产出的 PRD + 9 个 ADR + CONTEXT.md，无需额外 context bundle
- **Open Questions**：见 §0

---

## §2 Research Findings

### 事实与约束

1. **技术栈已定**（PRD §Solution + Implementation Decisions）：
   - 后端：FastAPI（Python ≥3.10）
   - 前端：Next.js（仅 BFF + UI，不承担业务逻辑）
   - DB：Postgres + pgvector + zhparser
   - 异步：Redis + Python worker（RQ 或 Celery）
   - 对象存储：MinIO
   - 部署：Docker Compose 一键起

2. **schema 预留策略**（ADR-0008 §MVP schema 预留但不实现）：
   - 业务表加 `tenant_id` 列（默认值 = bootstrap owner 的 tenant_id）
   - 创建空表 ready：`organizations` / `org_members` / `kb_shares` / `llm_providers` / `user_llm_keys` / `wiki_folders`
   - `sources.source_type` 列创建但只实现 manual adapter
   - `content_chunks.chunk_type` 列创建（默认 `document`，预留 `wiki_page` / `image_ocr` / `image_caption`）
   - `knowledge_bases` 加 IndexingStrategy 四开关（`vector_enabled` / `keyword_enabled` / `wiki_enabled` / `graph_enabled`），MVP 默认 `vector=true, keyword=true, wiki=true, graph=false`

3. **检索是核心模块**（PRD §Phase 划分行 258 + ADR-0009）：
   - 路径 B（knowledge_search）= 向量（pgvector halfvec）+ BM25（PG 全文 + zhparser）+ RRF 融合
   - halfvec 多维度共存：`embedding` 列声明为 `halfvec`（不带 N）+ `embedding_dim INT` + partial HNSW 索引 `WHERE embedding_dim = N` + 查询时 SQL 必须 cast `embedding::halfvec(N)`
   - wiki chunk boost 1.3 第一批不实现（无 wiki chunk 数据）

4. **鉴权极简**（ADR-0008 §MVP 鉴权极简）：
   - bootstrap owner：env var `BOOTSTRAP_OWNER_EMAIL` + `BOOTSTRAP_OWNER_PASSWORD` 启动时创建唯一 owner
   - JWT session：HS256，24h 有效期，无 refresh token（过期重登）
   - 无 workspace context 切换（只有一个 space）

5. **文档解析异步队列**（PRD §Phase 划分行 257 + ADR-0007）：
   - 上传 → MinIO 存原始文件 → Redis 队列 → Python worker 消费
   - PDF：pdfium / pdfplumber / unstructured
   - 分块：CJK 300 词 / 50 词 overlap（默认）
   - 嵌入：用系统兜底 LLM key（env var `LLM_API_KEY` + `LLM_PROVIDER`，第一批只用于 embedding）

6. **默认嵌入模型**：bge-m3（1024 维，中英双语，开源 SOTA）

### 风险与不确定项

1. **【高风险】pgvector halfvec 多维度 + partial HNSW**：
   - 应用层 SQL 必须 cast `embedding::halfvec(1024)`，否则规划器认不出索引会退化全表扫（pgvector issue #702 / #835）
   - 这是隐藏陷阱，不会报错只会静默性能崩塌
   - 缓解：code review checklist 钉死；DB 集成测试用 `EXPLAIN` 验证索引命中

2. **【高风险】zhparser 中文分词扩展**：
   - Postgres 官方镜像不带 zhparser，需要自定义 Dockerfile（基于 postgres:16 + 编译安装 zhparser）
   - 缓解：第一批 Dockerfile 就搞定，避免 P2 补扩展时需要重建数据

3. **【中风险】RRF 融合参数调优**：
   - RRF 的 `k` 参数（默认 60）和权重（向量 vs BM25）需要中英混排场景下调参
   - 缓解：MVP 用经验默认值（k=60，等权），P5 阶段做评估调参

4. **【中风险】PDF 解析质量**：
   - 不同 PDF 结构（扫描版 vs 文字版 / 双栏 / 表格）解析质量差异大
   - 缓解：第一批用 unstructured 库（支持多种 PDF 结构），扫描版 PDF 留给 P4（VLM OCR）

5. **【中风险】嵌入模型调用**：
   - 本地部署 bge-m3 需要装 PyTorch + 模型权重（~2GB）
   - API 调用需要网络依赖 + key 管理
   - 缓解：见 Open Question Q1，建议两者都支持

6. **【低风险】Next.js BFF 转发**：
   - Next.js 不承担业务逻辑，只做 SSR + BFF 转发到 FastAPI
   - 缓解：API Routes 严格只做鉴权转发，不写业务代码

### 关键技术验证点（第一批必须验证）

1. **pgvector halfvec partial HNSW 索引命中**：写 1024 维 chunks → `EXPLAIN ANALYZE` 查询 → 确认走 hnsw 索引而非 seq scan
2. **zhparser 中文分词**：插入含中文的 chunk → `to_tsvector('chinese_zh', content)` → 确认分词正确
3. **RRF 融合**：向量召回 top-10 + BM25 召回 top-10 → Python RRF 融合 → 确认融合后排序合理
4. **Docker Compose 一键起**：`docker-compose up` → 所有容器健康 → API 可访问

---

## §2.1 Next Actions

> 等用户回答 §0 的 Open Questions（Q1-Q5；Q6 可延后）后，进入下一步。

1. **【当前】等用户回答 Open Questions**（Q1 嵌入模型调用方式 / Q2 zhparser / Q3 MinIO / Q4 前端范围 / Q5 测试策略）
2. 回答齐了之后，**进入 Plan 阶段**：制定具体实现方案（文件结构 + 核心签名 + 原子化 checklist）
3. Plan 完成后，**等用户 `Plan Approved`**
4. 收到批准后，**进入 Execute 阶段**：按 checklist 实施
5. Execute 完成后，**进入 Review 阶段**：三轴评审

---

## §3 Innovate (Optional: Options & Decision)

### Skip

- **Skipped**: true
- **Reason**: 技术栈已由 PRD v4.2 + 9 个 ADR 完全锁定，§0 Open Questions 全部决策完毕，无遗留方案需要对比选择。

### 唯一小决策：嵌入 API provider

- **Selected**: **SiliconFlow 托管的 bge-m3**（`https://api.siliconflow.cn/v1/embeddings`，model=`BAAI/bge-m3`，1024 维）
- **Why**:
  1. 与本地部署的 bge-m3 维度完全一致（1024），未来 P2 切本地零成本（不需要重嵌入）
  2. SiliconFlow 是国内主流 LLM API 聚合平台，价格便宜
  3. 兼容 OpenAI 协议（`POST /v1/embeddings`），用 `openai` Python SDK 直接调用
- **Avoided**: OpenAI `text-embedding-3-small`（1536 维，与 bge-m3 不兼容，切本地要重嵌入）

---

## §4 Plan (Contract)

### §4.1 File Changes（项目结构）

全新项目，从零搭建。目录结构：

```
llm_wiki3.0/
├── docker-compose.yml              # 一键起服编排（postgres/redis/minio/backend/worker/frontend）
├── .env.example                    # 环境变量模板
├── Makefile                        # make up/down/migrate/test/logs
├── README.md                       # 启动指南
│
├── postgres/
│   └── Dockerfile                  # postgres:16 + 编译安装 pgvector + zhparser
│
├── backend/
│   ├── Dockerfile                  # python:3.11-slim + pip install
│   ├── pyproject.toml              # 依赖管理（uv 或 poetry）
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       └── 001_initial.py      # 初始 schema（核心表 + 空表预留 + 扩展 + 索引）
│   │
│   ├── app/
│   │   ├── main.py                # FastAPI 入口（lifespan: bootstrap owner）
│   │   ├── config.py              # pydantic-settings Settings
│   │   ├── database.py            # async engine + session factory
│   │   ├── deps.py                # get_db / get_current_user
│   │   │
│   │   ├── auth/
│   │   │   ├── jwt_handler.py     # HS256 create/decode
│   │   │   ├── password.py        # argon2id
│   │   │   ├── bootstrap.py       # ensure_bootstrap_owner
│   │   │   └── routes.py          # POST /api/auth/login
│   │   │
│   │   ├── models/
│   │   │   ├── base.py            # Declarative Base + TimestampMixin + TenantMixin
│   │   │   ├── user.py            # User + Tenant
│   │   │   ├── kb.py              # KnowledgeBase（含 IndexingStrategy 四开关）
│   │   │   ├── source.py          # Source（source_type + config JSONB）
│   │   │   ├── chunk.py           # ContentChunk（chunk_type + halfvec + embedding_dim + search_vector）
│   │   │   └── reserved.py        # 空表（P2 才用）：Organization/OrgMember/KBShare/LLMProvider/UserLLMKey/WikiFolder/WikiPage
│   │   │
│   │   ├── schemas/
│   │   │   ├── auth.py            # LoginRequest / TokenResponse
│   │   │   ├── kb.py              # KBCreate / KBResponse
│   │   │   ├── document.py        # DocumentUploadResponse / DocumentStatusResponse
│   │   │   └── search.py          # SearchResponse / ChunkHit
│   │   │
│   │   ├── routers/
│   │   │   ├── auth.py            # /api/auth/*
│   │   │   ├── kb.py              # /api/v1/kb
│   │   │   ├── document.py        # /api/v1/kb/{id}/documents
│   │   │   └── search.py          # /api/v1/kb/{id}/search
│   │   │
│   │   ├── services/
│   │   │   ├── kb_service.py      # create_kb / get_kb / list_kbs
│   │   │   ├── document_service.py # upload + get_status
│   │   │   ├── embedding_service.py # 调用 SiliconFlow bge-m3 API
│   │   │   ├── minio_service.py   # 原始文件存取
│   │   │   └── search_service.py  # vector_search + bm25_search + rrf_fuse
│   │   │
│   │   ├── workers/
│   │   │   ├── queue.py           # Redis RQ 队列
│   │   │   ├── worker.py          # RQ worker 启动入口
│   │   │   ├── parse_document.py  # 完整任务流程
│   │   │   └── chunker.py         # CJK 300 词 / 50 词 overlap
│   │   │
│   │   └── plugins/
│   │       └── chunk_rerank.py    # CHUNK_RERANK 接口（第一批只声明，不实现 boost）
│   │
│   └── tests/
│       ├── conftest.py            # testcontainers Postgres + pgvector + zhparser
│       ├── test_auth.py
│       ├── test_kb.py
│       ├── test_document.py
│       ├── test_search.py
│       └── test_halfvec.py        # 关键陷阱：halfvec cast + EXPLAIN 索引命中
│
├── frontend/
│   ├── Dockerfile                 # node:20-alpine + Next.js standalone
│   ├── package.json
│   ├── next.config.js
│   ├── tsconfig.json
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx               # 重定向到 /search
│   │   └── search/
│   │       └── page.tsx           # 搜索页
│   ├── components/
│   │   ├── SearchBox.tsx
│   │   └── ResultList.tsx
│   └── lib/
│       └── api.ts                 # BFF 转发到 FastAPI
│
└── mydocs/                        # 已有设计文档（不动）
```

**关键设计说明**：

- **postgres 镜像自定义**：官方 `postgres:16` 不带 pgvector / zhparser，必须自定义 Dockerfile 编译安装。这是第一批的基础设施依赖。
- **backend / worker 共享代码**：worker 容器复用 backend 代码（同一个 Dockerfile），只是启动命令不同（`uvicorn` vs `rq worker`）。
- **frontend 只做 BFF 转发**：Next.js 不承担业务逻辑，API Routes 只做鉴权转发到 FastAPI。
- **tests 用 testcontainers**：测试时起一次性 Postgres + pgvector + zhparser，避免污染开发数据库。
- **空表 reserved.py**：P2 才用的 7 张表（organization 等）在初始 migration 就创建（空表），避免 P2 时 ALTER TABLE 大表锁表风险（参 ADR-0008）。

---

---

### §4.2 Signatures（核心签名）

#### Python 后端

```python
# backend/app/config.py
class Settings(BaseSettings):
    postgres_dsn: str            # postgresql+asyncpg://...
    redis_url: str               # redis://redis:6379/0
    minio_endpoint: str          # minio:9000
    minio_access_key: str
    minio_secret_key: str
    jwt_secret: str
    jwt_expire_hours: int = 24
    bootstrap_owner_email: str
    bootstrap_owner_password: str
    embedding_api_base: str = "https://api.siliconflow.cn/v1"
    embedding_api_key: str
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024

# backend/app/auth/jwt_handler.py
def create_access_token(user_id: int) -> str: ...
def decode_token(token: str) -> dict: ...

# backend/app/auth/bootstrap.py
async def ensure_bootstrap_owner(db: AsyncSession) -> None: ...
# 启动 lifespan 调用；若 users 表为空，创建 user + tenant（默认 tenant_id=1）

# backend/app/models/kb.py
class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int]                    # 默认 bootstrap owner 的 tenant_id
    name: Mapped[str]
    embedding_model: Mapped[str]              # "BAAI/bge-m3"
    embedding_dim: Mapped[int]                # 1024
    vector_enabled: Mapped[bool] = True
    keyword_enabled: Mapped[bool] = True
    wiki_enabled: Mapped[bool] = True         # 默认 true，但第一批无 wiki 数据
    graph_enabled: Mapped[bool] = False

# backend/app/models/chunk.py
class ContentChunk(Base):
    __tablename__ = "content_chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int]
    tenant_id: Mapped[int]
    doc_id: Mapped[str]                       # UUID
    chunk_type: Mapped[str] = "document"      # document / wiki_page / image_ocr / image_caption
    text: Mapped[str]
    # embedding: halfvec 列（不带 N），DDL 在 migration 里手写（SQLAlchemy 不直接支持 halfvec）
    embedding_dim: Mapped[int]                # 1024
    # search_vector: tsvector 列（zhparser），DDL 在 migration 里手写
    wiki_page_id: Mapped[Optional[int]]       # 第一批可空

# backend/app/routers/kb.py
@router.post("", response_model=KBResponse)
async def create_kb(payload: KBCreate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)) -> KBResponse: ...

@router.get("/{kb_id}", response_model=KBResponse)
async def get_kb(kb_id: int, ...) -> KBResponse: ...

@router.get("", response_model=list[KBResponse])
async def list_kbs(...) -> list[KBResponse]: ...

# backend/app/routers/document.py
@router.post("/{kb_id}/documents", response_model=DocumentUploadResponse)
async def upload_document(kb_id: int, file: UploadFile = File(...), ...) -> DocumentUploadResponse: ...
# 上传 → MinIO 存原始 → Redis 入队 → 返回 doc_id + status=pending

@router.get("/{kb_id}/documents/{doc_id}", response_model=DocumentStatusResponse)
async def get_document_status(kb_id: int, doc_id: str, ...) -> DocumentStatusResponse: ...

# backend/app/routers/search.py
@router.get("/{kb_id}/search", response_model=SearchResponse)
async def search(
    kb_id: int,
    q: str = Query(...),
    mode: str = Query("rag", regex="^(rag|wiki)$"),  # 第一批只实现 rag；wiki 返回 400
    limit: int = Query(10, le=50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SearchResponse: ...

# backend/app/services/search_service.py
async def vector_search(
    db: AsyncSession, kb_id: int, query_embedding: list[float], embedding_dim: int, top_k: int = 20
) -> list[ChunkHit]:
    """
    SQL（关键：必须 cast 成 halfvec(N)，否则规划器认不出 partial HNSW 索引）：
      SELECT id, text, doc_id,
             (embedding::halfvec(:dim) <=> CAST(:query AS halfvec(:dim))) AS distance
      FROM content_chunks
      WHERE kb_id = :kb_id
        AND embedding_dim = :dim
        AND deleted_at IS NULL
        AND chunk_type = 'document'
      ORDER BY distance
      LIMIT :top_k
    """
    ...

async def bm25_search(
    db: AsyncSession, kb_id: int, query: str, top_k: int = 20
) -> list[ChunkHit]:
    """
    SQL（zhparser 中文分词）：
      SELECT id, text, doc_id,
             ts_rank_cd(search_vector, plainto_tsquery('chinese_zh', :query)) AS rank
      FROM content_chunks
      WHERE kb_id = :kb_id
        AND search_vector @@ plainto_tsquery('chinese_zh', :query)
        AND deleted_at IS NULL
        AND chunk_type = 'document'
      ORDER BY rank DESC
      LIMIT :top_k
    """
    ...

def rrf_fuse(
    vector_results: list[ChunkHit], bm25_results: list[ChunkHit], k: int = 60
) -> list[ChunkHit]:
    """RRF: score(d) = sum(1 / (k + rank_in_list)) over both lists; sort desc."""
    ...

# backend/app/services/embedding_service.py
async def embed_texts(texts: list[str]) -> list[list[float]]:
    """调用 SiliconFlow API（openai SDK，base_url 覆盖），返回 1024 维向量列表。"""
    ...

# backend/app/workers/parse_document.py
async def parse_document_task(doc_id: str) -> None:
    """
    1. MinIO 拉原始文件
    2. 按文件类型解析（pdfium/pdfplumber for PDF / markdown for MD / unstructured for Word）
    3. chunker.chunk_text(text, max_words=300, overlap=50)
    4. embedding_service.embed_texts(chunks)
    5. INSERT INTO content_chunks (..., chunk_type='document', embedding_dim=1024, ...)
    6. UPDATE documents SET status='processed' WHERE doc_id=...
    """
    ...

# backend/app/workers/chunker.py
def chunk_text(text: str, max_words: int = 300, overlap: int = 50) -> list[str]:
    """CJK 友好分块：按句子边界 + 词数控制；中文按字符，英文按 word，混合时按比例。"""
    ...
```

#### TypeScript 前端

```typescript
// frontend/lib/api.ts
export async function login(email: string, password: string): Promise<TokenResponse>;
export async function search(
  kbId: number, query: string, mode?: 'rag' | 'wiki'
): Promise<SearchResponse>;

// frontend/app/search/page.tsx
export default function SearchPage(): JSX.Element;

// frontend/components/SearchBox.tsx
export function SearchBox({ onSearch, loading }: { onSearch: (q: string) => void; loading: boolean }): JSX.Element;

// frontend/components/ResultList.tsx
export function ResultList({ results }: { results: ChunkHit[] }): JSX.Element;
```

#### 关键 SQL（DDL）

```sql
-- alembic/versions/001_initial.py 核心片段

CREATE EXTENSION IF NOT EXISTS vector;       -- pgvector
CREATE EXTENSION IF NOT EXISTS zhparser;     -- zhparser

-- zhparser 全文检索配置
CREATE TEXT SEARCH CONFIGURATION chinese_zh (PARSER = zhparser);
ALTER TEXT SEARCH CONFIGURATION chinese_zh
  ADD MAPPING FOR n,v,a,i,e,j WITH simple;

-- content_chunks 表（halfvec + tsvector）
CREATE TABLE content_chunks (
  id            BIGSERIAL PRIMARY KEY,
  kb_id         INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
  tenant_id     INT NOT NULL REFERENCES tenants(id),
  doc_id        UUID NOT NULL,
  chunk_type    TEXT NOT NULL DEFAULT 'document',
  text          TEXT NOT NULL,
  embedding     halfvec NOT NULL,            -- 不带 N，变长 halfvec
  embedding_dim INT NOT NULL,                -- 真实维度（1024）
  search_vector tsvector,                    -- 由 trigger 维护
  wiki_page_id  INT REFERENCES wiki_pages(id) ON DELETE CASCADE,
  created_at    TIMESTAMPTZ DEFAULT now(),
  deleted_at    TIMESTAMPTZ
);

-- partial HNSW 索引（按维度分别建索引）
CREATE INDEX content_chunks_embedding_1024_hnsw
  ON content_chunks
  USING hnsw ((embedding::halfvec(1024)) halfvec_cosine_ops)
  WHERE embedding_dim = 1024 AND deleted_at IS NULL;

-- GIN 索引 over search_vector
CREATE INDEX content_chunks_search_vector_gin
  ON content_chunks USING gin(search_vector)
  WHERE deleted_at IS NULL;

-- search_vector trigger（INSERT/UPDATE 时自动维护）
CREATE TRIGGER content_chunks_search_vector_trigger
  BEFORE INSERT OR UPDATE ON content_chunks
  FOR EACH ROW EXECUTE FUNCTION
  tsvector_update_trigger(search_vector, 'public.chinese_zh', text);
```

---

### §4.3 Implementation Checklist（原子化，按依赖顺序）

> 共 9 个阶段，~50 个原子任务。每阶段末尾有验证点。

#### 阶段 1：基础设施（Docker + 部署骨架）

- [ ] 1.1 `docker-compose.yml`：postgres / redis / minio / backend / worker / frontend 六个 service + healthcheck + volumes + networks
- [ ] 1.2 `postgres/Dockerfile`：基于 `postgres:16`，编译安装 `pgvector`（release tag）+ `zhparser`，自定义 entrypoint 自动 `CREATE EXTENSION`
- [ ] 1.3 `backend/Dockerfile`：`python:3.11-slim` + `pip install -e .` + 暴露 8000 端口
- [ ] 1.4 `backend/pyproject.toml`：依赖清单（fastapi / uvicorn[standard] / sqlalchemy[asyncio] / asyncpg / alembic / pydantic / pydantic-settings / python-jose[cryptography] / passlib[argon2] / openai / minio / redis / rq / unstructured / pdfium / pdfplumber / python-multipart / pytest / pytest-asyncio / testcontainers[postgres] / httpx）
- [ ] 1.5 `frontend/Dockerfile`：`node:20-alpine` + `npm ci` + `npm run build` + standalone output
- [ ] 1.6 `.env.example`：所有 env var 模板（含注释）
- [ ] 1.7 `Makefile`：`make up` / `make down` / `make migrate` / `make test` / `make logs` / `make shell`
- [ ] 1.8 `README.md`：5 分钟启动指南
- [ ] **1.9 验证**：`make up` 所有容器 healthcheck 通过 + `localhost:8000/docs` 可访问

#### 阶段 2：数据库 schema（Alembic migration）

- [ ] 2.1 初始化 Alembic：`alembic init alembic` + 配置 `alembic.ini` + `alembic/env.py`（异步 engine）
- [ ] 2.2 `backend/app/models/base.py`：Declarative Base + TimestampMixin（created_at/updated_at/deleted_at）
- [ ] 2.3 `backend/app/models/user.py` + `tenant.py`：User / Tenant
- [ ] 2.4 `backend/app/models/kb.py`：KnowledgeBase + IndexingStrategy 四开关
- [ ] 2.5 `backend/app/models/source.py`：Source（source_type + config + sync_cursor）
- [ ] 2.6 `backend/app/models/chunk.py`：ContentChunk（chunk_type + halfvec + embedding_dim + search_vector + wiki_page_id）
- [ ] 2.7 `backend/app/models/reserved.py`：7 张空表（Organization / OrgMember / KBShare / LLMProvider / UserLLMKey / WikiFolder / WikiPage）
- [ ] 2.8 `backend/alembic/versions/001_initial.py`：完整初始 migration（扩展 + 表 + 索引 + trigger）
  - `CREATE EXTENSION vector` + `CREATE EXTENSION zhparser`
  - `CREATE TEXT SEARCH CONFIGURATION chinese_zh` + mapping
  - 上述所有表（核心 + 空表）
  - partial HNSW 索引 `WHERE embedding_dim = 1024 AND deleted_at IS NULL`
  - GIN 索引 over search_vector
  - `tsvector_update_trigger` 维护 search_vector
- [ ] **2.9 验证**：`make migrate` 成功 + psql 连进去看表结构 + `SELECT * FROM pg_extension` 看扩展

#### 阶段 3：鉴权（bootstrap owner + JWT）

- [ ] 3.1 `backend/app/config.py`：pydantic-settings Settings 类（model_config 用 env_file=`.env`）
- [ ] 3.2 `backend/app/database.py`：`create_async_engine` + `async_sessionmaker`
- [ ] 3.3 `backend/app/auth/password.py`：`hash_password(pwd) -> str` + `verify_password(pwd, hash) -> bool`（argon2id）
- [ ] 3.4 `backend/app/auth/jwt_handler.py`：`create_access_token(user_id)` + `decode_token(token)`（HS256，过期时间从 config 读）
- [ ] 3.5 `backend/app/auth/bootstrap.py`：`ensure_bootstrap_owner(db)` —— 查 users 表为空则创建 user + tenant（同事务）
- [ ] 3.6 `backend/app/auth/routes.py`：`POST /api/auth/login`（email + password → JWT）
- [ ] 3.7 `backend/app/deps.py`：`get_db()` + `get_current_user(token = Depends(oauth2_scheme))`
- [ ] 3.8 `backend/app/main.py`：FastAPI app + `lifespan` 启动时调 `ensure_bootstrap_owner` + 注册路由
- [ ] **3.9 验证**：启动日志看到"bootstrap owner created" + curl 登录拿 JWT + 用 JWT 调 `/api/me` 返回 user 信息

#### 阶段 4：KB 创建 API

- [ ] 4.1 `backend/app/schemas/kb.py`：`KBCreate` / `KBResponse`（含 IndexingStrategy 四字段）
- [ ] 4.2 `backend/app/services/kb_service.py`：`create_kb`（默认 bge-m3 + 1024 维 + 混合 IndexingStrategy + tenant_id 默认 bootstrap owner）/ `get_kb` / `list_kbs`
- [ ] 4.3 `backend/app/routers/kb.py`：POST/GET 端点
- [ ] **4.4 验证**：curl 创建 KB → 返回 `{embedding_model: "BAAI/bge-m3", embedding_dim: 1024, vector_enabled: true, keyword_enabled: true, wiki_enabled: true, graph_enabled: false}`

#### 阶段 5：文档上传 + 异步解析

- [ ] 5.1 `backend/app/services/minio_service.py`：`upload_file(bucket, key, file)` + `get_file(bucket, key) -> bytes` + `ensure_bucket(bucket)`
- [ ] 5.2 `backend/app/workers/queue.py`：Redis RQ 队列初始化 + `enqueue_parse_document(doc_id)` 函数
- [ ] 5.3 `backend/app/workers/chunker.py`：`chunk_text(text, max_words=300, overlap=50) -> list[str]`（CJK 友好）
- [ ] 5.4 `backend/app/services/embedding_service.py`：`embed_texts(texts) -> list[list[float]]`（用 `openai` SDK，base_url 覆盖到 SiliconFlow）
- [ ] 5.5 `backend/app/workers/parse_document.py`：`parse_document_task(doc_id)` 完整流程（MinIO 拉文件 → 按类型解析 → 分块 → 嵌入 → INSERT content_chunks）
- [ ] 5.6 `backend/app/workers/worker.py`：RQ worker 启动入口（`rq worker --url redis://...`）
- [ ] 5.7 `backend/app/services/document_service.py`：`upload_document(kb_id, file)`（存 MinIO + 入队 + 创建 document 记录）/ `get_status(doc_id)`
- [ ] 5.8 `backend/app/routers/document.py`：`POST /{kb_id}/documents`（UploadFile）+ `GET /{kb_id}/documents/{doc_id}`
- [ ] 5.9 `backend/app/models/document.py`：Document 表（doc_id / kb_id / source_id / status / minio_key / created_at / processed_at）
- [ ] **5.10 验证**：curl 上传一个 PDF + 一个 MD → 轮询 `GET /documents/{doc_id}` 直到 status=processed → 查 DB `SELECT count(*) FROM content_chunks WHERE doc_id=...` 有值

#### 阶段 6：路径 B 检索

- [ ] 6.1 `backend/app/services/search_service.py`：
  - `vector_search`：raw SQL `SELECT ..., (embedding::halfvec(1024) <=> CAST(:q AS halfvec(1024))) AS distance ...`（**关键：cast 必须带维度**）
  - `bm25_search`：raw SQL `SELECT ..., ts_rank_cd(search_vector, plainto_tsquery('chinese_zh', :q)) AS rank ...`
  - `rrf_fuse`：纯 Python 函数，按 chunk_id 合并两路 rank，RRF 公式 `sum(1 / (k + rank))`
  - `search(db, kb_id, query, mode, limit)`：编排 embed query → vector_search → bm25_search → rrf_fuse → 返回 top-K
- [ ] 6.2 `backend/app/schemas/search.py`：`SearchResponse` / `ChunkHit`（id / text / score / doc_id / distance / rank）
- [ ] 6.3 `backend/app/routers/search.py`：`GET /{kb_id}/search`（mode=wiki 时返回 400 提示"第一批未实现，请用 mode=rag"）
- [ ] 6.4 `backend/app/plugins/chunk_rerank.py`：plugin 接口声明（`ChunkRerankPlugin` Protocol + 注册函数），第一批不实现 boost，留 TODO 注释
- [ ] **6.5 验证**：
  - 中文 query（如"知识库架构"）召回相关 chunks
  - 英文 query（如"vector database"）召回相关 chunks
  - 中英混排（如"RAG 检索增强"）召回
  - `EXPLAIN ANALYZE` 跑 vector_search SQL → 确认走 `Index Scan using content_chunks_embedding_1024_hnsw` 而非 `Seq Scan`
  - `EXPLAIN ANALYZE` 跑 bm25_search SQL → 确认走 `Bitmap Index Scan using content_chunks_search_vector_gin`

#### 阶段 7：最小前端（搜索页）

- [ ] 7.1 `frontend/` 初始化：Next.js 14（app router）+ TypeScript + Tailwind CSS
- [ ] 7.2 `frontend/lib/api.ts`：BFF 封装（login / search），用 `server-side` 调 FastAPI
- [ ] 7.3 `frontend/components/SearchBox.tsx`：query 输入框 + 提交按钮 + loading 状态
- [ ] 7.4 `frontend/components/ResultList.tsx`：top-K chunks 列表（title / score / text snippet / 来源文档名）
- [ ] 7.5 `frontend/app/search/page.tsx`：搜索页（SearchBox + ResultList + 选 KB 下拉）
- [ ] 7.6 `frontend/app/page.tsx`：重定向到 `/search`
- [ ] 7.7 `frontend/app/layout.tsx`：根布局
- [ ] **7.8 验证**：浏览器访问 `localhost:3000/search` → 输入 query → 看到 top-K chunks

#### 阶段 8：关键路径测试

- [ ] 8.1 `backend/tests/conftest.py`：testcontainers 启动 Postgres + pgvector + zhparser + Redis + MinIO（或用 docker-compose 的服务 + 测试数据库）
- [ ] 8.2 `backend/tests/test_auth.py`：bootstrap owner 创建 + login 返回 JWT + 错误密码 401 + JWT 过期 401
- [ ] 8.3 `backend/tests/test_kb.py`：创建 KB + 默认配置正确 + tenant_id 默认值 + list_kbs
- [ ] 8.4 `backend/tests/test_document.py`：上传 MD → 异步处理完成 → chunks 入库（chunk_type='document'）+ search_vector 有值
- [ ] 8.5 `backend/tests/test_search.py`：中文 / 英文 / 中英混排 query 都能召回 + RRF 融合后排序合理
- [ ] 8.6 `backend/tests/test_halfvec.py`（**最关键**）：
  - 写 1024 维 chunk
  - `EXPLAIN` 查询带 cast `embedding::halfvec(1024)` → 确认走 hnsw 索引
  - `EXPLAIN` 查询不带 cast → 确认走 seq scan（验证陷阱）
- [ ] **8.7 验证**：`pytest` 全部通过

#### 阶段 9：端到端验收

- [ ] 9.1 完整流程：`make up` → curl 登录 → curl 创建 KB → curl 上传 PDF → 轮询 status → curl 搜索 → 看到结果
- [ ] 9.2 浏览器：访问 `localhost:3000/search` → 输入 query → 看到结果
- [ ] 9.3 DB 层：psql 里跑 `EXPLAIN ANALYZE SELECT ... <=> ...` 确认 hnsw 命中
- [ ] 9.4 人工抽检：中文 query 5 条 + 英文 query 5 条，top-1 结果与 query 语义相关
- [ ] 9.5 Review 阶段：执行 `review_execute` 三轴评审

---

### §4.4 Spec Review Notes（建议性预审，Plan 完成后）

> 用户可在此后执行 `review_spec` 命令做正式预审；本节为 Agent 自评。

- **Spec Review Matrix（Agent 自评）**：

| Check | Verdict | Evidence |
|---|---|---|
| Requirement clarity & acceptance | PASS | §1 Goal / In-Scope / Out-of-Scope / 验收标准清晰；§0 Open Questions 全部决策 |
| Plan executability | PASS | §4.1 项目结构完整；§4.2 签名含关键 SQL；§4.3 checklist 9 阶段 ~50 任务原子化 |
| Risk / rollback readiness | PARTIAL | §2 标注了 5 个风险（halfvec cast / zhparser / RRF 调参 / PDF 解析 / 嵌入 API）；回滚策略未明写（建议每个阶段可独立回滚） |

- **Readiness Verdict**：**GO**（建议性）
- **Risks & Suggestions**：
  1. halfvec cast 是隐藏陷阱，已在 §4.3 阶段 6.5 / 阶段 8.6 双重验证点（EXPLAIN）
  2. zhparser 需要自定义 Postgres Dockerfile，建议阶段 1.2 优先验证（编译失败会卡住后续所有 DB 工作）
  3. RRF 调参第一批用经验默认值（k=60 等权），P5 再做评估
- **Phase Reminders**：Execute 阶段需在 §5 记录每个阶段的执行日志 + 偏差说明

---

## §5 Execute Log

> 待 Execute 阶段填充（需用户 `Plan Approved` 后才能开始）。

---

## §6 Review Verdict

> 待 Review 阶段填充。

---

## §7 Plan-Execution Diff

> 待 Review 阶段填充。

---

## §8 Archive Record

> 待 closure 阶段填充。
