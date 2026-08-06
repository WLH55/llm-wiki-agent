"""
检索服务（路径 B）

vector_search: pgvector 向量检索（halfvec cosine）
bm25_search:   PG 全文检索（zhparser 中文分词 + ts_rank_cd）
rrf_fuse:      Python 端 RRF 融合
search:        编排入口

【关键陷阱】vector_search 的 SQL 必须将 embedding cast 成 halfvec(N)，
否则规划器认不出 partial HNSW 索引会退化全表扫（参 ADR-0001）。
"""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import ResourceNotFoundException
from app.integrations.embedding import embed_one
from app.knowledge_bases.service.knowledge_base import get_rag_config
from app.models.kb import KnowledgeBase
from app.search.api.schemas import ChunkHit

logger = logging.getLogger(__name__)


async def vector_search(
    db: AsyncSession,
    kb_id: int,
    query_embedding: list[float],
    embedding_dim: int,
    top_k: int = 20,
) -> list[ChunkHit]:
    """pgvector 向量检索（cosine 距离）

    关键 SQL: (embedding::halfvec(N) <=> CAST(:q AS halfvec(N)))
    cast 必须带维度 N，否则不命中 partial HNSW 索引。
    """
    embedding_str = "[" + ",".join(f"{x:.7f}" for x in query_embedding) + "]"
    sql = text(
        f"""
        SELECT c.id, d.public_id::text AS doc_id, c.text,
               (c.embedding::halfvec({embedding_dim})
                <=> CAST(:q AS halfvec({embedding_dim}))) AS distance
        FROM content_chunks c
        JOIN documents d
          ON d.id = c.document_id
         AND d.active_revision_id = c.revision_id
        WHERE c.kb_id = :kb_id
          AND c.embedding_dim = :dim
        ORDER BY distance
        LIMIT :top_k
        """
    )
    result = await db.execute(
        sql,
        {
            "q": embedding_str,
            "kb_id": kb_id,
            "dim": embedding_dim,
            "top_k": top_k,
        },
    )
    hits: list[ChunkHit] = []
    for row in result:
        hits.append(
            ChunkHit(
                chunk_id=row.id,
                doc_id=row.doc_id,
                text=row.text,
                score=1.0 - row.distance,  # cosine 距离转相似度
                rank_source="vector",
                distance=float(row.distance),
            )
        )
    return hits


async def bm25_search(
    db: AsyncSession,
    kb_id: int,
    query: str,
    top_k: int = 20,
) -> list[ChunkHit]:
    """PG 全文检索（zhparser 中文分词 + ts_rank_cd）"""
    sql = text(
        """
        SELECT c.id, d.public_id::text AS doc_id, c.text, 1.0 AS rank
        FROM content_chunks c
        JOIN documents d
          ON d.id = c.document_id
         AND d.active_revision_id = c.revision_id
        WHERE c.kb_id = :kb_id
          AND c.text ILIKE :pattern
        ORDER BY c.id
        LIMIT :top_k
        """
    )
    result = await db.execute(
        sql, {"pattern": f"%{query}%", "kb_id": kb_id, "top_k": top_k}
    )
    hits: list[ChunkHit] = []
    for row in result:
        hits.append(
            ChunkHit(
                chunk_id=row.id,
                doc_id=row.doc_id,
                text=row.text,
                score=float(row.rank),
                rank_source="bm25",
                bm25_rank=float(row.rank),
            )
        )
    return hits


def rrf_fuse(
    vector_results: list[ChunkHit],
    bm25_results: list[ChunkHit],
    k: int = 60,
) -> list[ChunkHit]:
    """RRF 融合：score(d) = sum(1 / (k + rank_in_list))

    k=60 是经验默认值（参 spec §2 §1.7）。
    """
    scores: dict[int, float] = {}
    metadata: dict[int, ChunkHit] = {}

    for rank, hit in enumerate(vector_results):
        scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank + 1)
        if hit.chunk_id not in metadata:
            metadata[hit.chunk_id] = hit

    for rank, hit in enumerate(bm25_results):
        scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + 1.0 / (k + rank + 1)
        if hit.chunk_id not in metadata:
            metadata[hit.chunk_id] = hit

    fused: list[ChunkHit] = []
    for chunk_id, score in sorted(scores.items(), key=lambda x: -x[1]):
        hit = metadata[chunk_id].model_copy(update={"score": score, "rank_source": "rrf"})
        fused.append(hit)
    return fused


async def search(
    db: AsyncSession,
    kb_id: int,
    user_tenant_id: int,
    query: str,
    mode: str = "rag",
    limit: int = 10,
) -> list[ChunkHit]:
    """编排：embed query → 向量召回 + BM25 召回 → RRF 融合 → top-K"""
    kb: KnowledgeBase = await get_kb_by_id(db, kb_id, user_tenant_id)

    if mode == "wiki":
        # 第一批未实现路径 A wiki_search
        raise NotImplementedError("第一批未实现 mode=wiki，请用 mode=rag")

    # 定稿 schema：RAG 开关与 embedding 维度在 kb_rag_configs，KB 表不再持有。
    rag_config = await get_rag_config(db, kb_id)
    vector_enabled = rag_config.vector_enabled if rag_config else True
    keyword_enabled = rag_config.keyword_enabled if rag_config else True
    embedding_dim = rag_config.embedding_dim if rag_config else None

    if not vector_enabled and not keyword_enabled:
        return []

    top_k_each = settings.RAG_TOP_K_EACH
    rrf_k = settings.RAG_RRF_K

    vector_hits: list[ChunkHit] = []
    bm25_hits: list[ChunkHit] = []

    if vector_enabled and embedding_dim is not None:
        query_embedding = embed_one(query)
        vector_hits = await vector_search(
            db, kb.id, query_embedding, embedding_dim, top_k=top_k_each
        )
    elif vector_enabled:
        logger.warning(
            "kb_id=%s vector_enabled=True 但 embedding_dim 未配置，跳过向量召回", kb_id
        )

    if keyword_enabled:
        bm25_hits = await bm25_search(db, kb.id, query, top_k=top_k_each)

    fused = rrf_fuse(vector_hits, bm25_hits, k=rrf_k)

    # 第一批不做 wiki chunk boost（plugins/chunk_rerank.py 是占位）
    return fused[:limit]


async def get_kb_by_id(
    db: AsyncSession, kb_id: int, tenant_id: int
) -> KnowledgeBase:
    """根据 id + tenant_id 查 KB"""
    from sqlalchemy import select

    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == kb_id,
            KnowledgeBase.tenant_id == tenant_id,
            KnowledgeBase.deleted_at.is_(None),
        ).limit(1)
    )
    kb = result.scalar_one_or_none()
    if kb is None:
        raise ResourceNotFoundException(f"KB {kb_id} 不存在")
    return kb
