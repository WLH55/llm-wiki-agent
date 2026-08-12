"""
content_chunks 表的数据访问层

从 retrieval.py / rag_ingestion.py 迁入，分离 SQL 操作与业务逻辑。
"""
import hashlib

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chunk import ContentChunk


class ChunkRepository:
    """content_chunks 表的数据访问"""

    def __init__(self, db: AsyncSession):
        self.db = db


    async def vector_search(
        self,
        kb_id: int,
        query_embedding: list[float],
        embedding_dim: int,
        expanded_topk: int,
        threshold: float,
        top_k: int,
    ) -> list[dict]:
        """pgvector 向量检索，返回原始行字典列表"""
        embedding_str = "[" + ",".join(f"{x:.7f}" for x in query_embedding) + "]"
        sql = text(
            f"""
            SELECT * FROM (
                SELECT c.id, c.document_id, c.revision_id, c.text, c.chunk_index,
                       c.source_locator,
                       d.title AS document_title,
                       s.source_type,
                       (c.embedding::halfvec({embedding_dim})
                        <=> CAST(:q AS halfvec({embedding_dim}))) AS distance
                FROM content_chunks c
                JOIN documents d
                  ON d.id = c.document_id
                 AND d.active_revision_id = c.revision_id
                JOIN sources s
                  ON s.id = c.source_id
                WHERE c.kb_id = ANY(:kb_ids)
                  AND c.embedding_dim = :dim
                ORDER BY distance
                LIMIT :expanded_topk
            ) sub
            WHERE (1.0 - distance) >= :threshold
            LIMIT :top_k
            """
        )
        result = await self.db.execute(
            sql,
            {
                "q": embedding_str,
                "kb_ids": [kb_id],
                "dim": embedding_dim,
                "expanded_topk": expanded_topk,
                "threshold": threshold,
                "top_k": top_k,
            },
        )
        return [row._asdict() for row in result]


    async def bm25_search(
        self,
        kb_id: int,
        query: str,
        expanded_topk: int,
        threshold: float,
        top_k: int,
    ) -> list[dict]:
        """pg_search BM25 检索，返回原始行字典列表"""
        sql = text(
            """
            SELECT * FROM (
                SELECT c.id, c.document_id, c.revision_id, c.text, c.chunk_index,
                       c.source_locator,
                       d.title AS document_title,
                       s.source_type,
                       paradedb.score(c.id) AS bm25_score
                FROM content_chunks c
                JOIN documents d
                  ON d.id = c.document_id
                 AND d.active_revision_id = c.revision_id
                JOIN sources s
                  ON s.id = c.source_id
                WHERE c.kb_id = ANY(:kb_ids)
                  AND c.text @@@ paradedb.parse(:query)
                ORDER BY bm25_score DESC
                LIMIT :expanded_topk
            ) sub
            WHERE bm25_score >= :threshold
            LIMIT :top_k
            """
        )
        result = await self.db.execute(
            sql,
            {
                "query": query,
                "kb_ids": [kb_id],
                "expanded_topk": expanded_topk,
                "threshold": threshold,
                "top_k": top_k,
            },
        )
        return [row._asdict() for row in result]


    async def find_nearby(
        self,
        doc_id: int,
        rev_id: int,
        indices: list[int],
    ) -> list[dict]:
        """nearby 上下文增强：按 (document_id, revision_id, chunk_index) 批量查相邻块"""
        sql = text(
            """
            SELECT c.id, c.document_id, c.revision_id, c.text, c.chunk_index,
                   c.source_locator,
                   d.title AS document_title,
                   s.source_type
            FROM content_chunks c
            JOIN documents d
              ON d.id = c.document_id
             AND d.active_revision_id = c.revision_id
            JOIN sources s
              ON s.id = c.source_id
            WHERE c.document_id = :doc_id
              AND c.revision_id = :rev_id
              AND c.chunk_index = ANY(:indices)
            """
        )
        result = await self.db.execute(
            sql,
            {"doc_id": doc_id, "rev_id": rev_id, "indices": indices},
        )
        return [row._asdict() for row in result]


    async def exists_by_revision(self, revision_id: int) -> bool:
        """检查某 revision 是否已有候选 chunks"""
        result = await self.db.scalar(
            select(ContentChunk.id)
            .where(ContentChunk.revision_id == revision_id)
            .limit(1)
        )
        return result is not None


    async def bulk_insert_candidates(
        self,
        tenant_id: int,
        kb_id: int,
        source_id: int,
        document_id: int,
        revision_id: int,
        processing_run_id: int,
        chunks: list[str],
    ) -> None:
        """批量插入候选 chunks"""
        self.db.add_all(
            [
                ContentChunk(
                    tenant_id=tenant_id,
                    kb_id=kb_id,
                    source_id=source_id,
                    document_id=document_id,
                    revision_id=revision_id,
                    processing_run_id=processing_run_id,
                    chunk_index=index,
                    text=chunk,
                    token_count=max(1, len(chunk) // 4),
                    text_sha256=hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
                    source_locator={"chunk_index": index},
                )
                for index, chunk in enumerate(chunks)
            ]
        )


    async def load_candidates_by_revision(
        self, revision_id: int
    ) -> list[ContentChunk]:
        """按 revision_id 加载候选 chunks（按 chunk_index 排序）"""
        result = await self.db.execute(
            select(ContentChunk)
            .where(ContentChunk.revision_id == revision_id)
            .order_by(ContentChunk.chunk_index)
        )
        return list(result.scalars().all())


    async def update_embedding(
        self,
        chunk_id: int,
        revision_id: int,
        embedding_value: str,
        embedding_dim: int | None,
        embedding_run_id: int,
    ) -> None:
        """更新单个 chunk 的 embedding（仅当 embedding IS NULL）"""
        await self.db.execute(
            text(
                """
                UPDATE content_chunks
                SET embedding = CAST(:embedding AS halfvec),
                    embedding_dim = :embedding_dim,
                    embedding_run_id = :embedding_run_id
                WHERE id = :chunk_id
                  AND revision_id = :revision_id
                  AND embedding IS NULL
                """
            ),
            {
                "embedding": embedding_value,
                "embedding_dim": embedding_dim,
                "embedding_run_id": embedding_run_id,
                "chunk_id": chunk_id,
                "revision_id": revision_id,
            },
        )