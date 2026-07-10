"""
Document service：上传 + 状态查询
"""
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.exceptions import BusinessValidationException, ResourceNotFoundException
from app.models.document import Document
from app.models.user import User
from app.schemas.document import DocumentStatusResponse, DocumentUploadResponse
from app.services.kb_service import get_kb
from app.services.minio_service import upload_bytes
from app.workers.queue import enqueue_parse_document

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


async def upload_document(
    db: AsyncSession,
    kb_id: int,
    user: User,
    filename: str,
    content: bytes,
    content_type: str,
) -> DocumentUploadResponse:
    """上传文档 → MinIO → 入队异步解析"""
    kb = await get_kb(db, kb_id, user)

    if len(content) > MAX_FILE_SIZE:
        raise BusinessValidationException(
            f"文件过大: {len(content)} bytes（max={MAX_FILE_SIZE}）"
        )

    doc_id = uuid.uuid4()
    minio_key = f"{kb.id}/{doc_id}/{filename}"
    upload_bytes(minio_key, content, content_type or "application/octet-stream")

    doc = Document(
        tenant_id=user.tenant_id,
        kb_id=kb.id,
        doc_id=doc_id,
        original_filename=filename,
        minio_key=minio_key,
        status="pending",
    )
    db.add(doc)
    await db.commit()

    enqueue_parse_document(str(doc_id))

    logger.info(f"文档已上传: doc_id={doc_id} kb_id={kb.id} filename={filename}")

    return DocumentUploadResponse(
        doc_id=doc_id,
        status="pending",
        original_filename=filename,
    )


async def get_document_status(
    db: AsyncSession,
    kb_id: int,
    user: User,
    doc_id: uuid.UUID,
) -> DocumentStatusResponse:
    """查询文档处理状态"""
    kb = await get_kb(db, kb_id, user)
    from sqlalchemy import select

    result = await db.execute(
        select(Document).where(
            Document.doc_id == doc_id,
            Document.kb_id == kb.id,
            Document.tenant_id == user.tenant_id,
        ).limit(1)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise ResourceNotFoundException(f"文档 {doc_id} 不存在")

    return DocumentStatusResponse(
        doc_id=doc.doc_id,
        status=doc.status,
        original_filename=doc.original_filename,
        error_message=doc.error_message,
        processed_at=doc.processed_at,
    )
