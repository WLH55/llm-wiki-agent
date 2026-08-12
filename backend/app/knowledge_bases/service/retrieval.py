"""
知识库检索服务（P0 检索地基）

业务编排层：不直接操作数据库，通过 ChunkRepository / RagConfigRepository 访问数据。
- vector_search: pgvector 向量检索（halfvec cosine + 过检索 + 阈值子查询）
- bm25_search:   pg_search BM25 检索（chinese_lindera 分词 + paradedb.score()）
- rrf_fuse:      加权 RRF 融合（0.7:0.3, k=60）
- search:        编排入口（embed -> 双路过检索 -> 阈值过滤 -> RRF -> 截断 -> nearby 增强）

设计依据：mydocs/specs/2026-08-06_17-43_RAG知识库检索设计.md
"""
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.integrations.embedding import embed_one
from app.knowledge_bases.api.schemas import RetrievalResult
from app.knowledge_bases.repository.chunk_repo import ChunkRepository
from app.knowledge_bases.repository.kb_repo import RagConfigRepository

logger = logging.getLogger(__name__)


def _over_retrieve_topk(limit: int) -> int:
    """过检索 top_k：clamp(limit * factor, MIN, CAP)"""
    expanded = limit * settings.RAG_OVER_RETRIEVE_FACTOR
    return max(settings.RAG_OVER_RETRIEVE_MIN, min(expanded, settings.RAG_OVER_RETRIEVE_CAP))


async def vector_search(
    db: AsyncSession,
    kb_id: int,
    query_embedding: list[float],
    embedding_dim: int,
    top_k: int = 20,
    threshold: float = 0.15,
) -> list[RetrievalResult]:
    """pgvector 向量检索（cosine 距离 + 阈值过滤）

    关键 SQL: (embedding::halfvec(N) <=> CAST(:q AS halfvec(N)))
    cast 必须带维度 N，否则不命中 partial HNSW 索引（ADR-0001）。
    score = 1 - distance（cosine 相似度），低于 threshold 过滤。
    """
    repo = ChunkRepository(db)
    rows = await repo.vector_search(
        kb_id, query_embedding, embedding_dim,
        expanded_topk=_over_retrieve_topk(top_k),
        threshold=threshold,
        top_k=top_k,
    )
    hits: list[RetrievalResult] = []
    for row in rows:
        hits.append(
            RetrievalResult(
                chunk_id=row["id"],
                document_id=row["document_id"],
                revision_id=row["revision_id"],
                score=1.0 - float(row["distance"]),
                match_type="vector",
                text=row["text"],
                chunk_index=row["chunk_index"],
                source_locator=row["source_locator"] or {},
                document_title=row["document_title"] or "",
                source_type=row["source_type"] or "unknown",
            )
        )
    return hits


async def bm25_search(
    db: AsyncSession,
    kb_id: int,
    query: str,
    top_k: int = 20,
    threshold: float = 0.3,
) -> list[RetrievalResult]:
    """pg_search BM25 检索（chinese_lindera 分词 + paradedb.score()）

    使用 @@@ 查询操作符 + paradedb.score(id) 打分。
    score 归一化到 0-1，低于 threshold 过滤。
    """
    repo = ChunkRepository(db)
    rows = await repo.bm25_search(
        kb_id, query,
        expanded_topk=_over_retrieve_topk(top_k),
        threshold=threshold,
        top_k=top_k,
    )
    hits: list[RetrievalResult] = []
    for row in rows:
        hits.append(
            RetrievalResult(
                chunk_id=row["id"],
                document_id=row["document_id"],
                revision_id=row["revision_id"],
                score=float(row["bm25_score"]),
                match_type="bm25",
                text=row["text"],
                chunk_index=row["chunk_index"],
                source_locator=row["source_locator"] or {},
                document_title=row["document_title"] or "",
                source_type=row["source_type"] or "unknown",
            )
        )
    return hits


def rrf_fuse(
    vector_results: list[RetrievalResult],
    bm25_results: list[RetrievalResult],
    k: int = 60,
    vector_weight: float = 0.7,
    keyword_weight: float = 0.3,
) -> list[RetrievalResult]:
    """加权 RRF 融合

    score(d) = vector_weight/(k+rank_v) + keyword_weight/(k+rank_k)
    单路缺失时该路贡献为 0。
    k=60, 权重 0.7:0.3（WeKnora 同款）。
    """
    scores: dict[int, float] = {}
    metadata: dict[int, RetrievalResult] = {}
    # rank 从 1 开始
    for rank, hit in enumerate(vector_results):
        scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + vector_weight / (k + rank + 1)
        if hit.chunk_id not in metadata:
            metadata[hit.chunk_id] = hit
    for rank, hit in enumerate(bm25_results):
        scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + keyword_weight / (k + rank + 1)
        if hit.chunk_id not in metadata:
            metadata[hit.chunk_id] = hit
    fused: list[RetrievalResult] = []
    for chunk_id, score in sorted(scores.items(), key=lambda x: -x[1]):
        hit = metadata[chunk_id].model_copy(update={"score": score, "match_type": "rrf"})
        fused.append(hit)
    return fused


async def _enrich_context(
    db: AsyncSession, hits: list[RetrievalResult], top_n: int = 5
) -> None:
    """nearby 上下文增强：对 top-N 命中按 (document_id, revision_id) 批量取 chunk_index±1

    相邻块 match_type=nearby，填入 hit.context 列表。
    """
    if not hits:
        return
    # 只对 top-N 命中做增强
    targets = hits[:top_n]
    repo = ChunkRepository(db)
    # 收集所有需要查询的 (document_id, revision_id, chunk_index) 组合
    # 按 (document_id, revision_id) 分组，批量取相邻 chunk_index
    groups: dict[tuple[int, int], list[int]] = {}
    for hit in targets:
        key = (hit.document_id, hit.revision_id)
        indices = groups.setdefault(key, [])
        # 收集 ±1 的 chunk_index
        for idx in (hit.chunk_index - 1, hit.chunk_index + 1):
            if idx >= 0 and idx not in indices:
                indices.append(idx)
    if not groups:
        return
    # 批量查询相邻 chunk
    nearby_map: dict[int, RetrievalResult] = {}
    for (doc_id, rev_id), indices in groups.items():
        rows = await repo.find_nearby(doc_id, rev_id, indices)
        for row in rows:
            nearby_map[row["id"]] = RetrievalResult(
                chunk_id=row["id"],
                document_id=row["document_id"],
                revision_id=row["revision_id"],
                score=0.0,
                match_type="nearby",
                text=row["text"],
                chunk_index=row["chunk_index"],
                source_locator=row["source_locator"] or {},
                document_title=row["document_title"] or "",
                source_type=row["source_type"] or "unknown",
            )
    # 填入 hit.context
    for hit in targets:
        context_hits: list[RetrievalResult] = []
        for idx in (hit.chunk_index - 1, hit.chunk_index + 1):
            # 查找相邻 chunk（按 document_id+revision_id+chunk_index 匹配）
            for nearby in nearby_map.values():
                if (
                    nearby.document_id == hit.document_id
                    and nearby.revision_id == hit.revision_id
                    and nearby.chunk_index == idx
                ):
                    context_hits.append(nearby)
        hit.context = context_hits


async def search(
    db: AsyncSession,
    kb_id: int,
    query: str,
    limit: int = 10,
) -> list[RetrievalResult]:
    """编排：embed query -> 向量召回 + BM25 召回 -> 阈值过滤 -> 加权 RRF -> 截断 -> nearby 增强

    embedding Key 失效时降级为纯 BM25 检索（ADR-0020 联动）。
    """
    # 获取 RAG 配置
    rag_config_repo = RagConfigRepository(db)
    rag_config = await rag_config_repo.get_by_kb(kb_id)
    vector_enabled = rag_config.vector_enabled if rag_config else True
    keyword_enabled = rag_config.keyword_enabled if rag_config else True
    embedding_dim = rag_config.embedding_dim if rag_config else None
    if not vector_enabled and not keyword_enabled:
        return []
    top_k_each = settings.RAG_TOP_K_EACH
    rrf_k = settings.RAG_RRF_K
    vector_threshold = settings.RAG_VECTOR_THRESHOLD
    keyword_threshold = settings.RAG_KEYWORD_THRESHOLD
    vector_weight = settings.RAG_RRF_VECTOR_WEIGHT
    keyword_weight = settings.RAG_RRF_KEYWORD_WEIGHT
    vector_hits: list[RetrievalResult] = []
    bm25_hits: list[RetrievalResult] = []
    # 向量路：embedding 失效时降级
    if vector_enabled and embedding_dim is not None:
        try:
            query_embedding = embed_one(query)
            vector_hits = await vector_search(
                db, kb_id, query_embedding, embedding_dim,
                top_k=top_k_each, threshold=vector_threshold,
            )
        except Exception as e:
            logger.warning(
                "kb_id=%s embedding 调用失败，降级为纯 BM25 检索: %s", kb_id, e
            )
    elif vector_enabled:
        logger.warning(
            "kb_id=%s vector_enabled=True 但 embedding_dim 未配置，跳过向量召回", kb_id
        )
    # BM25 路
    if keyword_enabled:
        bm25_hits = await bm25_search(
            db, kb_id, query, top_k=top_k_each, threshold=keyword_threshold,
        )
    # RRF 融合
    fused = rrf_fuse(
        vector_hits, bm25_hits,
        k=rrf_k, vector_weight=vector_weight, keyword_weight=keyword_weight,
    )
    # 截断
    top_results = fused[:limit]
    # nearby 上下文增强
    await _enrich_context(db, top_results)
    return top_results