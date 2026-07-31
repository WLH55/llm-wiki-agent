"""Revision 化 RAG 摄入的业务 Handler。"""

import asyncio
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.integrations.embedding import embed_texts
from app.integrations.object_storage import get_bytes
from app.models.chunk import ContentChunk
from app.models.document import Document, DocumentRevision
from app.models.kb import KnowledgeBase
from app.parsers.core.errors import ParserAssetError
from app.parsers.service.asset import persist_parser_images
from app.parsers.service.dispatch import parse_document
from app.workers.broker import CRITICAL_QUEUE
from app.workers.chunker import chunk_text
from app.workers.executor import RunExecutionContext, TerminalTaskError
from app.workers.runtime import create_run_with_outbox


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
    if context.identity.scope_type != "revision":
        raise TerminalTaskError("invalid_scope", "document_process must target a revision")
    revision = await db.get(DocumentRevision, context.identity.scope_id)
    if revision is None or revision.deleted_at is not None:
        raise TerminalTaskError("revision_not_found", "target revision does not exist")
    document = await db.get(Document, revision.document_id)
    if (
        document is None
        or document.deleted_at is not None
        or document.tenant_id != context.identity.tenant_id
        or document.kb_id != context.identity.kb_id
    ):
        raise TerminalTaskError("document_not_found", "revision document is unavailable")
    return document, revision


async def document_process_handler(context: RunExecutionContext) -> None:
    """解析 Revision，持久化候选 chunks，并可靠投递独立的 embedding Run。"""
    async with context.session_factory() as db:
        document, revision = await _load_document_revision(db, context)
        kb = await db.get(KnowledgeBase, context.identity.kb_id)
        if kb is None or kb.tenant_id != context.identity.tenant_id:
            raise TerminalTaskError("kb_not_found", "revision knowledge base is unavailable")

    raw_bytes = await asyncio.to_thread(get_bytes, revision.storage_key)
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                parse_document,
                revision.original_filename,
                raw_bytes,
                revision.parser_engine,
            ),
            timeout=settings.PARSER_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise TerminalTaskError("timeout", "document parser timed out") from exc
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
                document.doc_id,
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
        raise TerminalTaskError("empty_content", "document parser returned no text chunks")

    async def write_candidate_chunks(db: AsyncSession, _: RunExecutionContext) -> None:
        # 结果写入与 Run 成功、下游 Outbox 同事务，避免候选块孤立或漏投递。
        live_document, live_revision = await _load_document_revision(db, context)
        existing = await db.scalar(
            select(ContentChunk.id)
            .where(ContentChunk.revision_id == live_revision.id)
            .limit(1)
        )
        if existing is not None:
            raise TerminalTaskError("candidate_chunks_exist", "revision already has candidate chunks")
        db.add_all(
            [
                ContentChunk(
                    tenant_id=context.identity.tenant_id,
                    kb_id=context.identity.kb_id,
                    doc_id=live_document.doc_id,
                    source_id=live_document.source_id,
                    document_id=live_document.id,
                    revision_id=live_revision.id,
                    processing_run_id=context.run_id,
                    chunk_index=index,
                    chunk_type="document",
                    text=chunk,
                    token_count=max(1, len(chunk) // 4),
                    text_sha256=sha256(chunk.encode("utf-8")).hexdigest(),
                    source_locator={"chunk_index": index},
                )
                for index, chunk in enumerate(chunks)
            ]
        )
        live_revision.status = "ready"
        live_revision.parse_metadata = metadata
        live_document.status = "processing"
        live_document.parse_metadata = metadata
        await create_run_with_outbox(
            db,
            tenant_id=context.identity.tenant_id,
            kb_id=context.identity.kb_id,
            run_type="rag_index",
            scope_type="revision",
            scope_id=live_revision.id,
            trigger_type="system",
            queue_name=CRITICAL_QUEUE,
            parent_run_id=context.run_id,
            options_snapshot={"document_process_run_id": context.run_id},
        )

    await context.commit_success(write_candidate_chunks)


async def rag_index_handler(context: RunExecutionContext) -> None:
    """为候选 chunks 写入 embedding，并在同一 fenced 事务中激活 Revision。"""
    async with context.session_factory() as db:
        _, revision = await _load_document_revision(db, context)
        kb = await db.get(KnowledgeBase, context.identity.kb_id)
        if kb is None or kb.tenant_id != context.identity.tenant_id:
            raise TerminalTaskError("kb_not_found", "revision knowledge base is unavailable")
        candidates = (
            await db.execute(
                select(ContentChunk)
                .where(ContentChunk.revision_id == revision.id)
                .order_by(ContentChunk.chunk_index)
            )
        ).scalars().all()

    if not candidates:
        raise TerminalTaskError("candidate_chunks_missing", "revision has no candidate chunks")
    if any(chunk.embedding_run_id is not None for chunk in candidates):
        raise TerminalTaskError("candidate_chunks_indexed", "revision chunks are already indexed")

    embeddings: list[list[float]] | None = None
    if kb.vector_enabled:
        embeddings = await asyncio.to_thread(embed_texts, [chunk.text for chunk in candidates])
        if len(embeddings) != len(candidates):
            raise TerminalTaskError(
                "embedding_count_mismatch",
                "embedding response count does not match candidate chunks",
            )
        if any(len(embedding) != kb.embedding_dim for embedding in embeddings):
            raise TerminalTaskError(
                "embedding_dimension_mismatch",
                "embedding response dimension does not match knowledge base",
            )

    async def write_embeddings_and_activate(
        db: AsyncSession,
        _: RunExecutionContext,
    ) -> None:
        live_document, live_revision = await _load_document_revision(db, context)
        live_candidates = (
            await db.execute(
                select(ContentChunk)
                .where(ContentChunk.revision_id == live_revision.id)
                .order_by(ContentChunk.chunk_index)
            )
        ).scalars().all()
        if len(live_candidates) != len(candidates):
            raise TerminalTaskError(
                "candidate_chunks_changed", "revision candidate chunks changed during indexing"
            )
        if any(chunk.embedding_run_id is not None for chunk in live_candidates):
            raise TerminalTaskError(
                "candidate_chunks_indexed", "revision chunks are already indexed"
            )

        if embeddings is not None:
            for chunk, embedding in zip(live_candidates, embeddings):
                embedding_value = "[" + ",".join(f"{value:.7f}" for value in embedding) + "]"
                await db.execute(
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
                        "embedding_dim": kb.embedding_dim,
                        "embedding_run_id": context.run_id,
                        "chunk_id": chunk.id,
                        "revision_id": live_revision.id,
                    },
                )

        live_revision.status = "ready"
        live_document.active_revision_id = live_revision.id
        live_document.status = "processed"
        live_document.error_message = ""
        live_document.parse_error_code = None
        live_document.processed_at = datetime.now(timezone.utc)

    await context.commit_success(write_embeddings_and_activate)
