"""
Document service：上传 + 状态查询
"""

import logging
import os
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BusinessValidationException, ResourceNotFoundException
from app.integrations.object_storage import upload_bytes
from app.knowledge_bases.service.knowledge_base import get_kb
from app.models.document import Document
from app.models.user import User
from app.parsers.api.schemas import DocumentStatusResponse, DocumentUploadResponse
from app.parsers.core.registry import BUILTIN_ENGINE
from app.parsers.core.registry import registry as parser_registry
from app.parsers.schemas import ParseErrorCode

logger = logging.getLogger(__name__)

PRODUCTION_FILE_TYPES = frozenset({"txt", "md", "markdown", "pdf", "docx", "xlsx", "csv", "pptx"})


def validate_parser_request(
    filename: str,
    content: bytes,
    parser_engine: str,
) -> tuple[str, str]:
    """校验生产格式白名单、文件预算与显式解析引擎。"""

    file_type = os.path.splitext(filename or "")[1].lstrip(".").lower()
    if file_type not in PRODUCTION_FILE_TYPES:
        raise BusinessValidationException(
            f"不支持的文件类型: {file_type or 'unknown'}",
            error_code=ParseErrorCode.UNSUPPORTED_TYPE.value,
        )
    if len(content) > settings.PARSER_MAX_FILE_BYTES:
        raise BusinessValidationException(
            f"文件过大: {len(content)} bytes（max={settings.PARSER_MAX_FILE_BYTES}）",
            error_code=ParseErrorCode.TOO_LARGE.value,
        )
    selected_engine = (parser_engine or BUILTIN_ENGINE).strip().lower()
    engine_status = parser_registry.get_engine_status(selected_engine)
    if (
        engine_status is None
        or not engine_status["available"]
        or file_type not in engine_status["file_types"]
    ):
        raise BusinessValidationException(
            f"解析引擎不可用或不支持该格式: {selected_engine}/{file_type}",
            error_code=ParseErrorCode.ENGINE_UNAVAILABLE.value,
        )
    return file_type, selected_engine


async def upload_document(
    db: AsyncSession,
    kb_id: int,
    user: User,
    filename: str,
    content: bytes,
    content_type: str,
    parser_engine: str = BUILTIN_ENGINE,
) -> DocumentUploadResponse:
    """上传文档 → MinIO → 入队异步解析"""
    kb = await get_kb(db, kb_id, user)

    _, selected_engine = validate_parser_request(filename, content, parser_engine)

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
        parser_engine=selected_engine,
        parse_metadata={},
    )
    db.add(doc)
    await db.commit()

    from app.workers.queue import enqueue_parse_document

    enqueue_parse_document(str(doc_id))

    logger.info(f"文档已上传: doc_id={doc_id} kb_id={kb.id} filename={filename}")

    return DocumentUploadResponse(
        doc_id=doc_id,
        status="pending",
        original_filename=filename,
        parser_engine=selected_engine,
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
        select(Document)
        .where(
            Document.doc_id == doc_id,
            Document.kb_id == kb.id,
            Document.tenant_id == user.tenant_id,
        )
        .limit(1)
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise ResourceNotFoundException(f"文档 {doc_id} 不存在")

    return DocumentStatusResponse(
        doc_id=doc.doc_id,
        status=doc.status,
        original_filename=doc.original_filename,
        error_message=doc.error_message,
        error_code=doc.parse_error_code,
        parser_engine=doc.parser_engine,
        parse_metadata=doc.parse_metadata,
        warnings=list((doc.parse_metadata or {}).get("warnings", [])),
        processed_at=doc.processed_at,
    )
