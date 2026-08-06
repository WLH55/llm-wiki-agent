"""
【最关键】halfvec 多维度 + partial HNSW 索引命中验证

参考 ADR-0001：SQL 必须把 embedding cast 成 halfvec(N)，
否则规划器认不出 partial HNSW 索引会退化成全表扫。

注意：空表时规划器不会选索引（Seq Scan 成本更低），
且其他测试残留的行会污染 ANALYZE 统计、导致规划器决策翻转。
因此本测试自持 content_chunks 表：播种前清空、用专用 kb_id 隔离、
播种/清理后各 ANALYZE 一次，保证统计与真实行数一致。

按 2026-08-02 定稿 schema：
- content_chunks 已删除 doc_id / chunk_type / search_vector / deleted_at；
- 中文分词由 pg_search 任务后续引入，keyword 召回暂时用 text ILIKE 兜底。
"""
import hashlib

import pytest
from sqlalchemy import text

_DIM = 1024
# 专用 kb_id：与其他测试（document_ingestion 等）的数据彻底隔离
_SEED_KB_ID = 990001
_SEED_TEXT_PREFIX = "seed chunk for halfvec test"


async def _seed_chunks(db, count: int = 5000, dim: int = _DIM) -> None:
    """灌入 count 条 embedding_dim=dim 的种子 chunk，供 EXPLAIN 使用。

    用单条 INSERT..SELECT 生成，避免逐行绑定 1024 维向量字符串；
    行数太少时规划器会选 Seq Scan（对小表排序成本更低），
    故默认灌 5000 行保证 HNSW 索引路径可被选中。
    """
    await db.execute(text("DELETE FROM content_chunks"))
    await db.commit()
    await db.execute(
        text(
            f"""
            INSERT INTO content_chunks
                (tenant_id, kb_id, source_id, document_id, revision_id,
                 processing_run_id, chunk_index, text, token_count,
                 text_sha256, embedding, embedding_dim, embedding_run_id)
            SELECT 1, {_SEED_KB_ID}, 1, 1, g, 1, 0,
                   '{_SEED_TEXT_PREFIX} ' || g,
                   16,
                   md5(g::text),
                   ('[' || (SELECT string_agg((random() * 2 - 1)::numeric(10, 6)::text, ',')
                            FROM generate_series(1, {dim})) || ']')::halfvec,
                   {dim},
                   1
            FROM generate_series(1, {count}) AS g
            """
        )
    )
    await db.commit()
    # 更新统计：空表时规划器预估 rows=1，不会选择 HNSW 索引
    await db.execute(text("ANALYZE content_chunks"))


async def _cleanup_seed(db) -> None:
    await db.execute(text("DELETE FROM content_chunks"))
    await db.commit()
    await db.execute(text("ANALYZE content_chunks"))


@pytest.mark.asyncio
async def test_halfvec_cast_hits_hnsw_index(db_session):
    """正向：带 cast 的 SQL 走 hnsw 索引"""
    await _seed_chunks(db_session)
    try:
        fake_vec = "[" + ",".join("0" for _ in range(_DIM)) + "]"
        explain_sql = text(
            f"""
            EXPLAIN
            SELECT id,
                   (embedding::halfvec({_DIM}) <=> CAST(:q AS halfvec({_DIM}))) AS distance
            FROM content_chunks
            WHERE kb_id = {_SEED_KB_ID} AND embedding_dim = {_DIM}
            ORDER BY distance
            LIMIT 10
            """
        )
        # 规划器对"自然偏好索引"的成本估算会随统计/页布局抖动，
        # 为确定性关闭 seqscan：若 cast 匹配 HNSW 索引则必走 Index Scan，
        # 若不匹配则退化成 Seq Scan，断言依然能抓住退化。
        await db_session.execute(text("SET LOCAL enable_seqscan = off"))
        result = await db_session.execute(explain_sql, {"q": fake_vec})
        plan = "\n".join(row[0] for row in result)

        # 关键断言：必须命中 hnsw 索引
        assert "content_chunks_embedding_1024_hnsw" in plan, (
            f"未命中 hnsw 索引，SQL 退化成全表扫。\nplan=\n{plan}"
        )
    finally:
        await _cleanup_seed(db_session)


@pytest.mark.asyncio
async def test_halfvec_no_cast_seq_scan(db_session):
    """反向：不带 cast 的 SQL 会退化成全表扫（陷阱展示）

    这是 ADR-0001 的核心教训——开发中常见错误。
    """
    await _seed_chunks(db_session)
    try:
        fake_vec = "[" + ",".join("0" for _ in range(_DIM)) + "]"
        # 故意不加 cast（错误示范）
        explain_sql = text(
            f"""
            EXPLAIN
            SELECT id, (embedding <=> CAST(:q AS halfvec({_DIM}))) AS distance
            FROM content_chunks
            WHERE kb_id = {_SEED_KB_ID} AND embedding_dim = {_DIM}
            ORDER BY distance
            LIMIT 10
            """
        )
        result = await db_session.execute(explain_sql, {"q": fake_vec})
        plan = "\n".join(row[0] for row in result)

        # 反向断言：不带 cast → Seq Scan（说明索引未命中）
        assert "Seq Scan" in plan, (
            f"预期 Seq Scan（未命中索引），实际 plan=\n{plan}"
        )
    finally:
        await _cleanup_seed(db_session)


@pytest.mark.asyncio
async def test_keyword_iliike_fallback(db_session):
    """定稿 schema 无 search_vector/zhparser，keyword 召回暂时走 text ILIKE

    先插入一条 chunk，再用 ILIKE 查询，确认兜底路径可用；
    pg_search 镜像就绪后此测试应替换为 BM25 语义测试。
    """
    await db_session.execute(
        text(
            """
            INSERT INTO content_chunks
                (tenant_id, kb_id, source_id, document_id, revision_id,
                 processing_run_id, chunk_index, text, token_count, text_sha256)
            VALUES
                (1, :kb_id, 1, 1, 1, 1, 0, '知识库 RAG 检索增强生成', 12, :sha)
            """
        ),
        {
            "kb_id": _SEED_KB_ID,
            "sha": hashlib.sha256("知识库 RAG 检索增强生成".encode()).hexdigest(),
        },
    )
    await db_session.commit()

    result = await db_session.execute(
        text(
            "SELECT id FROM content_chunks WHERE text ILIKE '%检索%' AND kb_id = :kb_id"
        ),
        {"kb_id": _SEED_KB_ID},
    )
    hits = list(result.scalars())
    assert hits, "ILIKE 兜底未命中刚插入的 chunk"

    await db_session.execute(
        text("DELETE FROM content_chunks WHERE id = :id"), {"id": hits[0]}
    )
    await db_session.commit()
