"""
【最关键】halfvec 多维度 + partial HNSW 索引命中验证

参 ADR-0001：SQL 必须将 embedding cast 成 halfvec(N)，
否则规划器认不出 partial HNSW 索引会退化全表扫。
"""
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_halfvec_cast_hits_hnsw_index(db_session):
    """正向：带 cast 的 SQL 走 hnsw 索引"""
    dim = 1024
    fake_vec = "[" + ",".join("0" for _ in range(dim)) + "]"

    explain_sql = text(
        f"""
        EXPLAIN
        SELECT id,
               (embedding::halfvec({dim}) <=> CAST(:q AS halfvec({dim}))) AS distance
        FROM content_chunks
        WHERE kb_id = 1 AND embedding_dim = {dim} AND deleted_at IS NULL
        ORDER BY distance
        LIMIT 10
        """
    )
    result = await db_session.execute(explain_sql, {"q": fake_vec})
    plan = "\n".join(row[0] for row in result)

    # 关键断言：必须命中 hnsw 索引
    assert "content_chunks_embedding_1024_hnsw" in plan, (
        f"未命中 hnsw 索引！SQL 退化全表扫。\nplan=\n{plan}"
    )


@pytest.mark.asyncio
async def test_halfvec_no_cast_seq_scan(db_session):
    """反向：不带 cast 的 SQL 会退化全表扫（陷阱展示）

    这是 ADR-0001 的核心警告——开发中常见错误。
    """
    dim = 1024
    fake_vec = "[" + ",".join("0" for _ in range(dim)) + "]"

    # 故意不 cast（错误示范）
    explain_sql = text(
        f"""
        EXPLAIN
        SELECT id, (embedding <=> CAST(:q AS halfvec({dim}))) AS distance
        FROM content_chunks
        WHERE kb_id = 1 AND embedding_dim = {dim} AND deleted_at IS NULL
        ORDER BY distance
        LIMIT 10
        """
    )
    result = await db_session.execute(explain_sql, {"q": fake_vec})
    plan = "\n".join(row[0] for row in result)

    # 反向断言：不带 cast → Seq Scan（说明索引未命中）
    assert "Seq Scan" in plan or "Bitmap" in plan, (
        f"预期 Seq Scan（未命中索引），实际 plan=\n{plan}"
    )


@pytest.mark.asyncio
async def test_zhparser_chinese_tokenizer(db_session):
    """zhparser 中文分词正常工作"""
    # 插入测试数据
    insert_sql = text(
        """
        INSERT INTO content_chunks
            (tenant_id, kb_id, doc_id, chunk_type, text, embedding, embedding_dim)
        VALUES
            (1, 1, '00000000-0000-0000-0000-000000000001',
             'document', '知识库 RAG 检索增强生成',
             '[0,0]'::halfvec, 2)
        RETURNING id, search_vector
        """
    )
    result = await db_session.execute(insert_sql)
    row = result.fetchone()
    await db_session.commit()

    assert row is not None, "插入失败"
    # search_vector 由 trigger 自动维护
    assert row[1] is not None, "search_vector 未由 trigger 维护"

    # 清理
    await db_session.execute(text("DELETE FROM content_chunks WHERE id = :id"), {"id": row[0]})
    await db_session.commit()
