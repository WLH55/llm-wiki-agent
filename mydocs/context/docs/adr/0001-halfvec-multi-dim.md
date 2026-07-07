# halfvec 多维度共存方案

每个 KB 创建时绑定嵌入模型（如 bge-m3 1024 维 / text-embedding-3-large 3072 维），库内所有 chunks 维度一致；不同 KB 可以用不同维度。`content_chunks.embedding` 列声明为 `halfvec`（不带 N，pgvector 允许变长）+ `embedding_dim INT` 字段记录真实维度，每个维度单独建 partial HNSW 索引 `WHERE embedding_dim = N` 配合表达式 `(embedding::halfvec(N))`。查询时 SQL 必须 cast 成相同 `halfvec(N)`，否则规划器认不出索引会退化全表扫（pgvector issue #702 / #835）。

## Considered Options

- **维度 padding 到 `halfvec(3072)`**（PRD v4.2 原文）： rejected。不同维度向量空间不兼容，把 1024 维向量零填充到 3072 维后做余弦相似度，归一化后所有 bge-m3 向量之间相似度接近 1，区分度崩塌。数学上不成立，不是设计选择。
- **全局统一一个嵌入模型**：rejected。失去 KB 创建时选模型的灵活性（不同语种、不同质量需求、模型版本演进），且模型升级时全量重嵌入代价大。
- **默认上 Milvus/Qdrant**：rejected for default。pgvector + partial HNSW 已能覆盖中小型团队场景，运维少一个组件。Milvus/Qdrant 留作 Phase 4 可插拔选项，超大规模或跨实例检索时再启用。
- **`halfvec` 不带 N + 暴力扫描**：rejected。partial HNSW 完全可用，没必要牺牲检索性能。

## Consequences

- **新增嵌入模型时需要追加 migration**：每个新维度 N 加一条 `CREATE INDEX ... USING hnsw ((embedding::halfvec(N)) halfvec_cosine_ops) WHERE (embedding_dim = N)`。这是有意识的成本——避免 silently 引入新模型后查询退化全表扫。
- **应用层 SQL 必须显式 cast**：Python 端用 SQLAlchemy + psycopg2 时，所有向量检索 SQL 都要写 `embedding::halfvec(%s)` 而不是直接 `embedding`，且参数要带维度。忘记 cast 不会报错，只会静默退化全表扫——这是隐藏陷阱，需要在代码 review checklist 里钉死。
- **存储减半**：1024 维从 4KB → 2KB，3072 维从 12KB → 6KB；HNSW 索引体积和查询时间同步减半。FP16 精度对语义检索召回率影响可忽略（业界大型 RAG 系统的标准做法）。

## 参考实现

Go 项目（参考路径）已实现此模式：
- `migrations/versioned/000002_embeddings.up.sql` — 建表 + 首批 partial HNSW 索引
- `migrations/versioned/000059_embeddings_hnsw_1024.up.sql` — 追加 bge-m3 1024 维索引
- `internal/application/repository/retriever/postgres/repository.go:384,387` — 查询时 cast

llm_wiki3.0 用 FastAPI + SQLAlchemy，**SQL migration 可直接照搬**，应用层 cast 逻辑用 psycopg2 的 `SqlExpr` 或原生 SQL 实现（不要用 SQLAlchemy ORM 隐藏 cast）。
