"""
异步解析文档任务

流程：
1. 查 document 记录
2. 标记 processing
3. MinIO 拉文件
4. 按文件类型解析（PDF / MD / Word / TXT）
5. 分块（CJK 300 词 / 50 词 overlap）
6. 调嵌入 API（SiliconFlow bge-m3）
7. 写 content_chunks（embedding 用 raw SQL，因为 SQLAlchemy 不支持 halfvec）
8. 标记 processed
"""
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session_factory
from app.models.document import Document
from app.services.embedding_service import embed_texts
from app.services.minio_service import get_bytes
from app.workers.chunker import chunk_text
from app.workers.parsers import parse_by_filename

logger = logging.getLogger(__name__)


async def parse_document_task(doc_id_str: str) -> None:
    """主流程：异步解析文档并入库"""
    doc_id = UUID(doc_id_str)
    async with async_session_factory() as db:
        doc = await _get_doc(db, doc_id)
        if doc is None:
            logger.error(f"文档不存在: {doc_id}")
            return

        try:
            await _mark_status(db, doc, "processing")

            raw_bytes = get_bytes(doc.minio_key)
            full_text = parse_by_filename(doc.original_filename, raw_bytes)
            chunks_text = chunk_text(full_text, max_words=300, overlap=50)

            if not chunks_text:
                await _mark_status(db, doc, "processed", error="无文本内容")
                logger.warning(f"文档 {doc_id} 无文本内容")
                return

            embeddings = embed_texts(chunks_text)
            if len(embeddings) != len(chunks_text):
                raise RuntimeError(
                    f"嵌入数与块数不匹配: chunks={len(chunks_text)} embeddings={len(embeddings)}"
                )

            await _insert_chunks(db, doc, chunks_text, embeddings)
            await _mark_status(db, doc, "processed")

            logger.info(f"文档 {doc_id} 处理完成: {len(chunks_text)} chunks")

        except Exception as e:
            logger.error(f"文档 {doc_id} 处理失败: {e}", exc_info=True)
            await _mark_status(db, doc, "failed", error=str(e))


async def _get_doc(db: AsyncSession, doc_id: UUID) -> Document | None:
    result = await db.execute(
        select(Document).where(Document.doc_id == doc_id).limit(1)
    )
    return result.scalar_one_or_none()


async def _mark_status(
    db: AsyncSession, doc: Document, status: str, error: str = ""
) -> None:
    """更新文档状态"""
    doc.status = status
    doc.error_message = error
    if status == "processed":
        doc.processed_at = datetime.now(timezone.utc)
    await db.commit()


async def _insert_chunks(
    db: AsyncSession,
    doc: Document,
    chunks_text: list[str],
    embeddings: list[list[float]],
) -> None:
    """批量插入 content_chunks（embedding 用 raw SQL cast 成 halfvec）"""
    for chunk_text_value, embedding in zip(chunks_text, embeddings):
        embedding_str = "[" + ",".join(f"{x:.7f}" for x in embedding) + "]"
        await db.execute(
            text(
                """
                INSERT INTO content_chunks
                    (tenant_id, kb_id, doc_id, source_id, chunk_type,
                     text, embedding, embedding_dim)
                VALUES
                    (:tenant_id, :kb_id, :doc_id, :source_id, 'document',
                     :text, CAST(:embedding AS halfvec), :embedding_dim)
                """
            ),
            {
                "tenant_id": doc.tenant_id,
                "kb_id": doc.kb_id,
                "doc_id": str(doc.doc_id),
                "source_id": doc.source_id,
                "text": chunk_text_value,
                "embedding": embedding_str,
                "embedding_dim": settings.EMBEDDING_DIM,
            },
        )
    await db.commit()
