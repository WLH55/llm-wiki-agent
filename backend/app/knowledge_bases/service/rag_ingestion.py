"""Revision 化 RAG 摄入的业务 Handler。"""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.integrations.embedding import embed_texts
from app.integrations.object_storage import get_bytes
from app.knowledge_bases.repository.chunk_repo import ChunkRepository
from app.knowledge_bases.repository.document_repo import (
    DocumentRepository,
    DocumentRevisionRepository,
)
from app.knowledge_bases.repository.kb_repo import (
    KnowledgeBaseRepository,
    RagConfigRepository,
)
from app.knowledge_bases.service.chunker import chunk_text
from app.models.document import Document, DocumentRevision
from app.parsers.core.errors import ParserAssetError
from app.parsers.service.asset import persist_parser_images
from app.parsers.service.parse_pool import parse_in_subprocess
from app.workers import (
    ErrorCode,
    RunExecutionContext,
    RunType,
    ScopeType,
    SpanName,
    TerminalTaskError,
    TriggerType,
    begin_span,
    create_run,
    end_span,
    enqueue_run,
    fail_span,
    mark_run_enqueue_failed,
    register_run_handler,
)

logger = logging.getLogger(__name__)


def _parse_metadata(result) -> dict:
    metadata = dict(result.metadata)
    metadata["engine"] = result.engine
    metadata["warnings"] = list(result.warnings)
    metadata.pop("error", None)
    return metadata


async def _load_document_revision(
    db: AsyncSession,
    context: RunExecutionContext,
) -> tuple[Document, DocumentRevision]:
    if context.identity.scope_type != ScopeType.REVISION:
        raise TerminalTaskError(
            ErrorCode.INVALID_SCOPE, "document_process must target a revision"
        )
    rev_repo = DocumentRevisionRepository(db)
    doc_repo = DocumentRepository(db)
    revision = await rev_repo.get_by_id(context.identity.scope_id)
    if revision is None or revision.deleted_at is not None:
        raise TerminalTaskError(
            ErrorCode.REVISION_NOT_FOUND, "target revision does not exist"
        )
    document = await doc_repo.get_by_id(revision.document_id)
    if (
        document is None
        or document.tenant_id != context.identity.tenant_id
        or document.kb_id != context.identity.kb_id
    ):
        raise TerminalTaskError(
            ErrorCode.DOCUMENT_NOT_FOUND, "revision document is unavailable"
        )
    return document, revision


@register_run_handler(RunType.DOCUMENT_PROCESS)
async def document_process_handler(context: RunExecutionContext) -> None:
    """解析 Revision，持久化候选 chunks，并投递独立的 embedding Run。"""
    async with context.session_factory() as db:
        document, revision = await _load_document_revision(db, context)
        kb_repo = KnowledgeBaseRepository(db)
        kb = await kb_repo.get_for_user(context.identity.kb_id, context.identity.tenant_id)
        if kb is None:
            raise TerminalTaskError(
                ErrorCode.KB_NOT_FOUND, "revision knowledge base is unavailable"
            )

    # span: parse（解析文档 + 分块）
    await begin_span(
        context,
        SpanName.PARSE,
        input_summary={
            "filename": revision.original_filename,
            "parser_engine": revision.parser_engine,
        },
    )
    try:
        raw_bytes = await asyncio.to_thread(get_bytes, revision.storage_key)
        # 解析在子进程池执行：超时杀进程、崩溃隔离，失败收敛为 error_code
        result = await parse_in_subprocess(
            revision.original_filename,
            raw_bytes,
            revision.parser_engine,
        )
        if result.error_code is not None:
            raise TerminalTaskError(
                result.error_code.value,
                str(result.metadata.get("error", result.error_code.value)),
            )
        parsed_content = result.content
        metadata = _parse_metadata(result)
        if result.images:
            try:
                parsed_content, persisted_images = await asyncio.to_thread(
                    persist_parser_images,
                    document.kb_id,
                    document.public_id,
                    parsed_content,
                    result.images,
                    settings.PARSER_MAX_TOTAL_IMAGE_BYTES,
                )
            except ParserAssetError as exc:
                raise TerminalTaskError(exc.error_code.value, str(exc)) from exc
            metadata["images"] = persisted_images
        chunks = chunk_text(
            parsed_content,
            max_words=kb.chunk_size_tokens,
            overlap=kb.chunk_overlap_tokens,
        )
        if not chunks:
            raise TerminalTaskError(
                ErrorCode.EMPTY_CONTENT, "document parser returned no text chunks"
            )
        await end_span(
            context,
            SpanName.PARSE,
            output_summary={
                "chunk_count": len(chunks),
                "image_count": len(result.images),
            },
        )
    except Exception as exc:
        await fail_span(
            context,
            SpanName.PARSE,
            error_code=getattr(exc, "error_code", ErrorCode.UNEXPECTED_EXCEPTION),
            error_message=str(exc),
        )
        raise

    # span: persist（写 chunks + 创建子 Run）
    child_run_id: int | None = None

    async def write_candidate_chunks(db: AsyncSession, _: RunExecutionContext) -> None:
        nonlocal child_run_id
        live_document, live_revision = await _load_document_revision(db, context)
        chunk_repo = ChunkRepository(db)
        if await chunk_repo.exists_by_revision(live_revision.id):
            raise TerminalTaskError(
                ErrorCode.CANDIDATE_CHUNKS_EXIST,
                "revision already has candidate chunks",
            )
        await chunk_repo.bulk_insert_candidates(
            tenant_id=context.identity.tenant_id,
            kb_id=context.identity.kb_id,
            source_id=live_document.source_id,
            document_id=live_document.id,
            revision_id=live_revision.id,
            processing_run_id=context.run_id,
            chunks=chunks,
        )
        live_revision.status = "ready"
        live_revision.parse_metadata = metadata
        child_run = await create_run(
            db,
            tenant_id=context.identity.tenant_id,
            kb_id=context.identity.kb_id,
            run_type=RunType.RAG_INDEX,
            scope_type=ScopeType.REVISION,
            scope_id=live_revision.id,
            trigger_type=TriggerType.SYSTEM,
            parent_run_id=context.run_id,
            options_snapshot={"document_process_run_id": context.run_id},
        )
        child_run_id = child_run.id

    await begin_span(context, SpanName.PERSIST, input_summary={"chunk_count": len(chunks)})
    try:
        await context.commit_success(write_candidate_chunks)
        await end_span(
            context,
            SpanName.PERSIST,
            output_summary={"child_run_id": child_run_id},
        )
    except Exception as exc:
        await fail_span(
            context,
            SpanName.PERSIST,
            error_code=getattr(exc, "error_code", ErrorCode.UNEXPECTED_EXCEPTION),
            error_message=str(exc),
        )
        raise

    # DB 事务已提交，入队子 Run；入队失败时立即标子 Run failed（不等 Reaper 兜底）
    if child_run_id is not None:
        try:
            enqueue_run(RunType.RAG_INDEX, child_run_id)
        except Exception:
            logger.exception("enqueue child rag_index run failed: run_id=%s", child_run_id)
            async with context.session_factory() as db:
                async with db.begin():
                    await mark_run_enqueue_failed(
                        db,
                        child_run_id,
                        error_message="enqueue rag_index run failed",
                    )


@register_run_handler(RunType.RAG_INDEX)
async def rag_index_handler(context: RunExecutionContext) -> None:
    """为候选 chunks 写入 embedding，并在同一事务中激活 Revision。"""
    async with context.session_factory() as db:
        document, revision = await _load_document_revision(db, context)
        kb_repo = KnowledgeBaseRepository(db)
        kb = await kb_repo.get_for_user(context.identity.kb_id, context.identity.tenant_id)
        if kb is None:
            raise TerminalTaskError(
                ErrorCode.KB_NOT_FOUND, "revision knowledge base is unavailable"
            )
        rag_config_repo = RagConfigRepository(db)
        rag_config = await rag_config_repo.get_by_kb(context.identity.kb_id)
        vector_enabled = rag_config.vector_enabled if rag_config is not None else True
        embedding_dim = rag_config.embedding_dim if rag_config is not None else None
        chunk_repo = ChunkRepository(db)
        candidates = await chunk_repo.load_candidates_by_revision(revision.id)

    if not candidates:
        raise TerminalTaskError(
            ErrorCode.CANDIDATE_CHUNKS_MISSING, "revision has no candidate chunks"
        )
    if any(chunk.embedding_run_id is not None for chunk in candidates):
        raise TerminalTaskError(
            ErrorCode.CANDIDATE_CHUNKS_INDEXED,
            "revision chunks are already indexed",
        )

    # span: embed（生成 embeddings）
    await begin_span(
        context,
        SpanName.EMBED,
        input_summary={
            "chunk_count": len(candidates),
            "vector_enabled": vector_enabled,
        },
    )
    try:
        embeddings: list[list[float]] | None = None
        if vector_enabled:
            embeddings = await asyncio.to_thread(
                embed_texts,
                # 嵌入输入加文档标题前缀（仅新文档生效，提升检索质量）
                [f"{document.title}\n{chunk.text}" for chunk in candidates],
            )
            if len(embeddings) != len(candidates):
                raise TerminalTaskError(
                    ErrorCode.EMBEDDING_COUNT_MISMATCH,
                    "embedding response count does not match candidate chunks",
                )
            if embedding_dim is not None and any(len(embedding) != embedding_dim for embedding in embeddings):
                raise TerminalTaskError(
                    ErrorCode.EMBEDDING_DIMENSION_MISMATCH,
                    "embedding response dimension does not match knowledge base",
                )
        await end_span(
            context,
            SpanName.EMBED,
            output_summary={
                "embedded": len(embeddings) if embeddings is not None else 0
            },
        )
    except Exception as exc:
        await fail_span(
            context,
            SpanName.EMBED,
            error_code=getattr(exc, "error_code", ErrorCode.UNEXPECTED_EXCEPTION),
            error_message=str(exc),
        )
        raise

    # span: activate（写 embeddings + 激活 Revision）
    async def write_embeddings_and_activate(
        db: AsyncSession,
        _: RunExecutionContext,
    ) -> None:
        live_document, live_revision = await _load_document_revision(db, context)
        chunk_repo = ChunkRepository(db)
        live_candidates = await chunk_repo.load_candidates_by_revision(live_revision.id)
        if len(live_candidates) != len(candidates):
            raise TerminalTaskError(
                ErrorCode.CANDIDATE_CHUNKS_CHANGED,
                "revision candidate chunks changed during indexing",
            )
        if any(chunk.embedding_run_id is not None for chunk in live_candidates):
            raise TerminalTaskError(
                ErrorCode.CANDIDATE_CHUNKS_INDEXED,
                "revision chunks are already indexed",
            )

        if embeddings is not None:
            chunk_repo = ChunkRepository(db)
            for chunk, embedding in zip(live_candidates, embeddings):
                embedding_value = "[" + ",".join(f"{value:.7f}" for value in embedding) + "]"
                await chunk_repo.update_embedding(
                    chunk_id=chunk.id,
                    revision_id=live_revision.id,
                    embedding_value=embedding_value,
                    embedding_dim=embedding_dim,
                    embedding_run_id=context.run_id,
                )

        live_revision.status = "ready"
        live_document.active_revision_id = live_revision.id

    await begin_span(
        context,
        SpanName.ACTIVATE,
        input_summary={"embedding_count": len(embeddings) if embeddings else 0},
    )
    try:
        await context.commit_success(write_embeddings_and_activate)
        await end_span(context, SpanName.ACTIVATE, output_summary={"activated": True})
    except Exception as exc:
        await fail_span(
            context,
            SpanName.ACTIVATE,
            error_code=getattr(exc, "error_code", ErrorCode.UNEXPECTED_EXCEPTION),
            error_message=str(exc),
        )
        raise
