"""
检索 service 层行为契约测试

测试 knowledge_bases.service.retrieval 模块：
- rrf_fuse 加权数学（纯函数，不需 DB）
- _over_retrieve_topk clamp 逻辑（纯函数，不需 DB）
- RetrievalResult 数据结构完整性

需要 DB 的集成测试（阈值过滤/bm25/vector/nearby/空结果）在人工验收阶段执行。
"""
import pytest

from app.config import settings
from app.knowledge_bases.service.retrieval import _over_retrieve_topk, rrf_fuse
from app.knowledge_bases.api.schemas import RetrievalResult


def _make_hit(chunk_id: int, score: float = 0.5, match_type: str = "vector") -> RetrievalResult:
    """构造测试用 RetrievalResult"""
    return RetrievalResult(
        chunk_id=chunk_id,
        document_id=1,
        revision_id=1,
        score=score,
        match_type=match_type,
        text=f"chunk {chunk_id}",
        chunk_index=chunk_id,
        document_title="test doc",
        source_type="manual",
        source_locator={},
    )


# ========== rrf_fuse 加权数学 ==========


def test_rrf_fuse_weighted_score():
    """RRF 融合：加权分数 = vector_weight/(k+rank_v) + keyword_weight/(k+rank_k)"""
    vector_hits = [_make_hit(1), _make_hit(2)]
    bm25_hits = [_make_hit(1), _make_hit(3)]
    k = 60
    vw = settings.RAG_RRF_VECTOR_WEIGHT  # 0.7
    kw = settings.RAG_RRF_KEYWORD_WEIGHT  # 0.3
    fused = rrf_fuse(vector_hits, bm25_hits, k=k, vector_weight=vw, keyword_weight=kw)
    # chunk 1: vector rank=1, bm25 rank=1 -> vw/(k+1) + kw/(k+1)
    # chunk 2: vector rank=2 -> vw/(k+2)
    # chunk 3: bm25 rank=2 -> kw/(k+2)
    expected_1 = vw / (k + 1) + kw / (k + 1)
    expected_2 = vw / (k + 2)
    expected_3 = kw / (k + 2)
    score_map = {h.chunk_id: h.score for h in fused}
    assert abs(score_map[1] - expected_1) < 1e-10
    assert abs(score_map[2] - expected_2) < 1e-10
    assert abs(score_map[3] - expected_3) < 1e-10


def test_rrf_fuse_single_vector_only():
    """单路向量：bm25 缺失时 keyword 贡献为 0"""
    vector_hits = [_make_hit(1), _make_hit(2)]
    bm25_hits: list[RetrievalResult] = []
    k = 60
    vw = settings.RAG_RRF_VECTOR_WEIGHT
    kw = settings.RAG_RRF_KEYWORD_WEIGHT
    fused = rrf_fuse(vector_hits, bm25_hits, k=k, vector_weight=vw, keyword_weight=kw)
    assert len(fused) == 2
    # 只有向量路贡献
    assert abs(fused[0].score - vw / (k + 1)) < 1e-10
    assert fused[0].match_type == "rrf"


def test_rrf_fuse_single_bm25_only():
    """单路 BM25：vector 缺失时 vector 贡献为 0"""
    vector_hits: list[RetrievalResult] = []
    bm25_hits = [_make_hit(1), _make_hit(2)]
    k = 60
    vw = settings.RAG_RRF_VECTOR_WEIGHT
    kw = settings.RAG_RRF_KEYWORD_WEIGHT
    fused = rrf_fuse(vector_hits, bm25_hits, k=k, vector_weight=vw, keyword_weight=kw)
    assert len(fused) == 2
    assert abs(fused[0].score - kw / (k + 1)) < 1e-10


def test_rrf_fuse_dedup_same_chunk():
    """同一 chunk 在两路出现时分数累加"""
    vector_hits = [_make_hit(1)]
    bm25_hits = [_make_hit(1)]
    k = 60
    vw = settings.RAG_RRF_VECTOR_WEIGHT
    kw = settings.RAG_RRF_KEYWORD_WEIGHT
    fused = rrf_fuse(vector_hits, bm25_hits, k=k, vector_weight=vw, keyword_weight=kw)
    assert len(fused) == 1
    expected = vw / (k + 1) + kw / (k + 1)
    assert abs(fused[0].score - expected) < 1e-10


def test_rrf_fuse_sorted_desc():
    """融合结果按分数降序排列"""
    vector_hits = [_make_hit(10), _make_hit(20), _make_hit(30)]
    bm25_hits = [_make_hit(30), _make_hit(20)]
    fused = rrf_fuse(vector_hits, bm25_hits)
    scores = [h.score for h in fused]
    assert scores == sorted(scores, reverse=True)


def test_rrf_fuse_empty_both():
    """两路都空 -> 空结果"""
    fused = rrf_fuse([], [])
    assert fused == []


# ========== _over_retrieve_topk clamp ==========


def test_over_retrieve_normal():
    """正常范围：limit * factor"""
    result = _over_retrieve_topk(10)
    # 10 * 5 = 50，在 [50, 500] 范围内
    assert result == 50


def test_over_retrieve_min_clamp():
    """小 limit 时 clamp 到 MIN"""
    result = _over_retrieve_topk(1)
    # 1 * 5 = 5 < 50 -> clamp 到 50
    assert result == settings.RAG_OVER_RETRIEVE_MIN


def test_over_retrieve_cap_clamp():
    """大 limit 时 clamp 到 CAP"""
    result = _over_retrieve_topk(200)
    # 200 * 5 = 1000 > 500 -> clamp 到 500
    assert result == settings.RAG_OVER_RETRIEVE_CAP


# ========== RetrievalResult 数据结构 ==========


def test_retrieval_result_defaults():
    """RetrievalResult 默认值"""
    hit = RetrievalResult(
        chunk_id=1, document_id=1, revision_id=1, score=0.5,
        text="test", chunk_index=0,
    )
    assert hit.match_type == "rrf"
    assert hit.context == []
    assert hit.document_title == ""
    assert hit.source_type == "unknown"
    assert hit.source_locator == {}
    assert hit.citation_id is None
