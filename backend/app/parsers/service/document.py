"""
Document service：上传 + 状态查询
"""

import logging
import os
import uuid
from dataclasses import dataclass
from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BusinessValidationException, ResourceNotFoundException
from app.integrations.object_storage import delete_object, upload_bytes
from app.knowledge_bases.service.knowledge_base import get_kb
from app.models.document import Document, DocumentRevision
from app.models.source import Source
from app.models.task_runtime import ProcessingRun
from app.models.user import User
from app.parsers.api.schemas import (
    DocumentStatusResponse,
    DocumentUploadResponse,
    ParserEngineInfo,
    ParserEnginesResponse,
)
from app.parsers.core.registry import BUILTIN_ENGINE
from app.parsers.core.registry import registry as parser_registry
from app.parsers.core.schemas import ParseErrorCode
from app.workers import DEFAULT_QUEUE, create_run_with_outbox

logger = logging.getLogger(__name__)

BYTES_PER_MEGABYTE = 1024 * 1024

PRODUCTION_FILE_TYPES = frozenset(
    {
        "txt",
        "md",
        "markdown",
        "pdf",
        "docx",
        "doc",
        "xlsx",
        "xls",
        "csv",
        "pptx",
        "html",
        "htm",
        "mhtml",
        "mht",
        "epub",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
        "bmp",
        "tif",
        "tiff",
    }
)


@dataclass(frozen=True)
class DocumentProcessRun:
    """一次上传创建的文档、候选版本和首个处理 Run 的稳定标识。"""

    document_id: int
    revision_id: int
    run_id: int
    doc_id: uuid.UUID


def _format_megabytes(size_bytes: int) -> str:
    return f"{size_bytes / BYTES_PER_MEGABYTE:.2f} MB"


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
            f"文件过大: {_format_megabytes(len(content))}（最大 {_format_megabytes(settings.PARSER_MAX_FILE_BYTES)}）",
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


async def create_document_process_run(
    db: AsyncSession,
    *,
    tenant_id: int,
    kb_id: int,
    source_id: int,
    filename: str,
    content: bytes,
    media_type: str,
    storage_key: str,
    parser_engine: str,
    requested_by_user_id: int | None,
) -> DocumentProcessRun:
    """在调用方事务中创建上传记录、不可变 Revision 与可靠投递 Run。"""
    doc_id = uuid.uuid4()
    document = Document(
        tenant_id=tenant_id,
        kb_id=kb_id,
        source_id=source_id,
        doc_id=doc_id,
        source_document_key=str(doc_id),
        title=filename,
        original_filename=filename,
        minio_key=storage_key,
        status="pending",
        parser_engine=parser_engine,
        parse_metadata={},
    )
    db.add(document)
    await db.flush()
    revision = DocumentRevision(
        document_id=document.id,
        revision_no=1,
        original_filename=filename,
        media_type=media_type,
        size_bytes=len(content),
        content_sha256=sha256(content).hexdigest(),
        storage_key=storage_key,
        parser_engine=parser_engine,
        status="pending",
        parse_metadata={},
        created_by_user_id=requested_by_user_id,
    )
    db.add(revision)
    await db.flush()
    run = await create_run_with_outbox(
        db,
        tenant_id=tenant_id,
        kb_id=kb_id,
        run_type="document_process",
        scope_type="revision",
        scope_id=revision.id,
        trigger_type="manual",
        queue_name=DEFAULT_QUEUE,
        options_snapshot={"parser_engine": parser_engine},
        requested_by_user_id=requested_by_user_id,
    )
    return DocumentProcessRun(
        document_id=document.id,
        revision_id=revision.id,
        run_id=run.id,
        doc_id=document.doc_id,
    )


async def get_or_create_manual_source(
    db: AsyncSession,
    *,
    tenant_id: int,
    kb_id: int,
) -> Source:
    """为手动上传复用同一 Source，并由数据库处理首次并发创建。"""
    await db.execute(
        insert(Source)
        .values(
            tenant_id=tenant_id,
            kb_id=kb_id,
            source_type="manual",
            name="Manual uploads",
            config={},
            sync_cursor="",
        )
        .on_conflict_do_nothing(
            index_elements=["tenant_id", "kb_id", "source_type"],
            index_where=(Source.source_type == "manual") & Source.deleted_at.is_(None),
        )
    )
    source = (
        await db.execute(
            select(Source)
            .where(
                Source.tenant_id == tenant_id,
                Source.kb_id == kb_id,
                Source.source_type == "manual",
                Source.deleted_at.is_(None),
            )
            .order_by(Source.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if source is None:
        raise RuntimeError("manual source missing after conflict-safe upsert")
    return source


def list_parser_engines() -> ParserEnginesResponse:
    """汇总生产白名单与各引擎可实际上传格式（registry 格式与生产白名单取交集）。"""
    uploadable = sorted(PRODUCTION_FILE_TYPES)
    engines = [
        ParserEngineInfo(
            name=status["name"],
            description=status["description"],
            available=status["available"],
            unavailable_reason=status["unavailable_reason"],
            file_types=sorted(
                t for t in status["file_types"] if t in PRODUCTION_FILE_TYPES
            ),
        )
        for status in parser_registry.list_engines()
    ]
    return ParserEnginesResponse(uploadable_file_types=uploadable, engines=engines)


async def upload_document(
    db: AsyncSession,
    kb_id: int,
    user: User,
    filename: str,
    content: bytes,
    content_type: str,
    parser_engine: str = BUILTIN_ENGINE,
) -> DocumentUploadResponse:
    """上传对象后，原子创建 Revision、Run 与待发布 Outbox。"""
    kb = await get_kb(db, kb_id, user)
    _, selected_engine = validate_parser_request(filename, content, parser_engine)
    upload_id = uuid.uuid4()
    minio_key = f"{kb.id}/{upload_id}/{filename}"
    upload_bytes(minio_key, content, content_type or "application/octet-stream")
    try:
        source = await get_or_create_manual_source(
            db,
            tenant_id=user.tenant_id,
            kb_id=kb.id,
        )
        created = await create_document_process_run(
            db,
            tenant_id=user.tenant_id,
            kb_id=kb.id,
            source_id=source.id,
            filename=filename,
            content=content,
            media_type=content_type or "application/octet-stream",
            storage_key=minio_key,
            parser_engine=selected_engine,
            requested_by_user_id=user.id,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        try:
            delete_object(minio_key)
        except Exception:
            logger.warning("上传事务失败后的 MinIO 对象清理失败: key=%s", minio_key, exc_info=True)
        raise
    doc_id = created.doc_id
    logger.info(f"文档已上传: doc_id={doc_id} kb_id={kb.id} filename={filename}")
    return DocumentUploadResponse(
        doc_id=created.doc_id,
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
    latest_revision = (
        await db.execute(
            select(DocumentRevision)
            .where(
                DocumentRevision.document_id == doc.id,
                DocumentRevision.deleted_at.is_(None),
            )
            .order_by(DocumentRevision.revision_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    latest_run = None
    if latest_revision is not None:
        latest_run = (
            await db.execute(
                select(ProcessingRun)
                .where(
                    ProcessingRun.scope_type == "revision",
                    ProcessingRun.scope_id == latest_revision.id,
                )
                .order_by(ProcessingRun.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    status = doc.status
    error_message = doc.error_message
    error_code = doc.parse_error_code
    if latest_run is not None:
        if latest_run.status == "failed":
            status = "failed"
            error_message = latest_run.error_message
            error_code = latest_run.error_code
        elif latest_run.status == "running":
            status = "processing"
        elif latest_run.status == "pending":
            status = "pending"
        elif (
            latest_run.status == "succeeded"
            and latest_revision is not None
            and doc.active_revision_id == latest_revision.id
        ):
            status = "processed"

    parse_metadata = (
        latest_revision.parse_metadata if latest_revision is not None else doc.parse_metadata
    )
    return DocumentStatusResponse(
        doc_id=doc.doc_id,
        status=status,
        original_filename=doc.original_filename,
        error_message=error_message,
        error_code=error_code,
        parser_engine=doc.parser_engine,
        parse_metadata=parse_metadata,
        warnings=list((parse_metadata or {}).get("warnings", [])),
        processed_at=doc.processed_at,
    )
