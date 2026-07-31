"""Revision 化上传与可靠任务投递的数据库契约测试。"""

from collections.abc import AsyncIterator
from hashlib import sha256

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text

from app.models.chunk import ContentChunk
from app.models.database import async_engine, async_session_factory
from app.models.document import Document, DocumentRevision
from app.models.kb import KnowledgeBase
from app.models.source import Source
from app.models.task_runtime import ProcessingRun, TaskOutbox
from app.models.user import Tenant, User

TEST_TENANT_ID = 98_003
TEST_KB_ID = 203


async def _delete_ingestion_rows() -> None:
    """删除本模块创建的关联记录，避免影响全局 Outbox 领取用例。"""
    async with async_session_factory() as db:
        document_ids = select(Document.id).where(Document.tenant_id == TEST_TENANT_ID)
        revision_ids = select(DocumentRevision.id).where(
            DocumentRevision.document_id.in_(document_ids)
        )
        run_ids = select(ProcessingRun.id).where(ProcessingRun.tenant_id == TEST_TENANT_ID)
        await db.execute(delete(TaskOutbox).where(TaskOutbox.run_id.in_(run_ids)))
        await db.execute(delete(ProcessingRun).where(ProcessingRun.tenant_id == TEST_TENANT_ID))
        await db.execute(delete(ContentChunk).where(ContentChunk.tenant_id == TEST_TENANT_ID))
        await db.execute(delete(DocumentRevision).where(DocumentRevision.id.in_(revision_ids)))
        await db.execute(delete(Document).where(Document.id.in_(document_ids)))
        await db.execute(delete(Source).where(Source.tenant_id == TEST_TENANT_ID))
        await db.execute(delete(KnowledgeBase).where(KnowledgeBase.id == TEST_KB_ID))
        await db.execute(delete(User).where(User.tenant_id == TEST_TENANT_ID))
        await db.execute(delete(Tenant).where(Tenant.id == TEST_TENANT_ID))
        await db.commit()


@pytest_asyncio.fixture(autouse=True)
async def clean_ingestion_rows() -> AsyncIterator[None]:
    """此用例直接验证提交后的关联记录，按专用 tenant 前后清理。"""
    await async_engine.dispose()
    await _delete_ingestion_rows()
    yield
    await _delete_ingestion_rows()
    await async_engine.dispose()


@pytest.mark.asyncio
async def test_upload_runtime_creates_revision_run_and_outbox_in_one_commit():
    from app.parsers.service.document import create_document_process_run

    content = b"# Reliable RAG upload\n"
    async with async_session_factory() as db:
        async with db.begin():
            db.add(Tenant(id=TEST_TENANT_ID, name="ingestion-runtime-test"))
            await db.flush()
            db.add(
                KnowledgeBase(
                    id=TEST_KB_ID,
                    tenant_id=TEST_TENANT_ID,
                    name="ingestion-runtime-test",
                    embedding_model="test-embedding",
                    embedding_dim=3,
                )
            )
            await db.flush()
            source = Source(
                tenant_id=TEST_TENANT_ID,
                kb_id=TEST_KB_ID,
                source_type="manual",
                name="Manual uploads",
            )
            db.add(source)
            await db.flush()
            created = await create_document_process_run(
                db,
                tenant_id=TEST_TENANT_ID,
                kb_id=TEST_KB_ID,
                source_id=source.id,
                filename="guide.md",
                content=content,
                media_type="text/markdown",
                storage_key="203/revision-test/guide.md",
                parser_engine="builtin",
                requested_by_user_id=None,
            )

    async with async_session_factory() as db:
        document = await db.get(Document, created.document_id)
        revision = await db.get(DocumentRevision, created.revision_id)
        run = await db.get(ProcessingRun, created.run_id)
        outbox = (
            await db.execute(select(TaskOutbox).where(TaskOutbox.run_id == created.run_id))
        ).scalar_one()

    assert document is not None
    assert document.source_id == source.id
    assert document.active_revision_id is None
    assert revision is not None
    assert revision.document_id == document.id
    assert revision.revision_no == 1
    assert revision.content_sha256 == sha256(content).hexdigest()
    assert revision.status == "pending"
    assert run is not None
    assert run.run_type == "document_process"
    assert run.scope_type == "revision"
    assert run.scope_id == revision.id
    assert run.status == "pending"
    assert outbox.task_name == "process_run"
    assert outbox.queue_name == "llmwiki:tasks:default"
    assert outbox.published_at is None


@pytest.mark.asyncio
async def test_upload_service_creates_reliable_run_instead_of_direct_rq_enqueue(monkeypatch):
    from app.parsers.service import document as document_service

    content = b"# Upload service runtime\n"
    monkeypatch.setattr(document_service, "upload_bytes", lambda *args: None)
    async with async_session_factory() as db:
        async with db.begin():
            tenant = Tenant(id=TEST_TENANT_ID, name="ingestion-upload-test")
            db.add(tenant)
            await db.flush()
            kb = KnowledgeBase(
                id=TEST_KB_ID,
                tenant_id=tenant.id,
                name="ingestion-upload-test",
                embedding_model="test-embedding",
                embedding_dim=3,
            )
            user = User(
                tenant_id=tenant.id,
                email="ingestion-upload-test@example.local",
                password_hash="not-used-by-this-test",
            )
            db.add_all([kb, user])

        result = await document_service.upload_document(
            db,
            kb.id,
            user,
            "guide.md",
            content,
            "text/markdown",
        )

    async with async_session_factory() as db:
        document = (
            await db.execute(select(Document).where(Document.doc_id == result.doc_id))
        ).scalar_one()
        revision = (
            await db.execute(
                select(DocumentRevision).where(DocumentRevision.document_id == document.id)
            )
        ).scalar_one()
        run = (
            await db.execute(
                select(ProcessingRun).where(
                    ProcessingRun.scope_type == "revision",
                    ProcessingRun.scope_id == revision.id,
                )
            )
        ).scalar_one()
        outbox = (
            await db.execute(select(TaskOutbox).where(TaskOutbox.run_id == run.id))
        ).scalar_one()

    assert result.status == "pending"
    assert document.source_id is not None
    assert revision.content_sha256 == sha256(content).hexdigest()
    assert run.run_type == "document_process"
    assert outbox.task_name == "process_run"


@pytest.mark.asyncio
async def test_upload_service_deletes_object_when_database_commit_fails(monkeypatch):
    """数据库提交失败时，不保留没有对应 Revision 的 MinIO 对象。"""
    from app.parsers.service import document as document_service

    uploaded_keys: list[str] = []
    deleted_keys: list[str] = []
    monkeypatch.setattr(
        document_service,
        "upload_bytes",
        lambda key, *_: uploaded_keys.append(key),
    )
    monkeypatch.setattr(
        document_service,
        "delete_object",
        lambda key: deleted_keys.append(key),
        raising=False,
    )

    async with async_session_factory() as db:
        async with db.begin():
            tenant = Tenant(id=TEST_TENANT_ID, name="upload-compensation-test")
            db.add(tenant)
            await db.flush()
            kb = KnowledgeBase(
                id=TEST_KB_ID,
                tenant_id=TEST_TENANT_ID,
                name="upload-compensation-test",
                embedding_model="test-embedding",
                embedding_dim=3,
            )
            user = User(
                tenant_id=TEST_TENANT_ID,
                email="upload-compensation@example.local",
                password_hash="not-used-by-this-test",
            )
            db.add_all([kb, user])

        async def fail_commit() -> None:
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(db, "commit", fail_commit)
        with pytest.raises(RuntimeError, match="database unavailable"):
            await document_service.upload_document(
                db,
                kb.id,
                user,
                "compensation.md",
                b"# compensation\n",
                "text/markdown",
            )

    assert len(uploaded_keys) == 1
    assert deleted_keys == uploaded_keys


@pytest.mark.asyncio
async def test_database_enforces_one_active_manual_source_per_knowledge_base():
    """并发上传依赖数据库唯一索引收敛到唯一 manual Source。"""
    async with async_session_factory() as db:
        index_definition = (
            await db.execute(
                text(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = current_schema() "
                    "AND indexname = 'uq_sources_manual_active_per_kb'"
                )
            )
        ).scalar_one_or_none()

    assert index_definition is not None
    assert "tenant_id, kb_id, source_type" in index_definition
    assert "'manual'::text" in index_definition
    assert "deleted_at IS NULL" in index_definition


@pytest.mark.asyncio
async def test_document_process_handler_writes_candidate_chunks_and_index_run(monkeypatch):
    from app.parsers.core.schemas import ParseResult
    from app.parsers.service.document import create_document_process_run
    from app.workers.executor import ExecutionOutcome, execute_run_message
    from app.workers.rag_ingestion import document_process_handler

    content = b"# Candidate chunks\n"
    async with async_session_factory() as db:
        async with db.begin():
            db.add(Tenant(id=TEST_TENANT_ID, name="ingestion-handler-test"))
            await db.flush()
            db.add(
                KnowledgeBase(
                    id=TEST_KB_ID,
                    tenant_id=TEST_TENANT_ID,
                    name="ingestion-handler-test",
                    embedding_model="test-embedding",
                    embedding_dim=3,
                )
            )
            await db.flush()
            source = Source(
                tenant_id=TEST_TENANT_ID,
                kb_id=TEST_KB_ID,
                source_type="manual",
                name="Manual uploads",
            )
            db.add(source)
            await db.flush()
            created = await create_document_process_run(
                db,
                tenant_id=TEST_TENANT_ID,
                kb_id=TEST_KB_ID,
                source_id=source.id,
                filename="guide.md",
                content=content,
                media_type="text/markdown",
                storage_key="203/candidate-handler/guide.md",
                parser_engine="builtin",
                requested_by_user_id=None,
            )

    from app.workers import rag_ingestion

    monkeypatch.setattr(rag_ingestion, "get_bytes", lambda _: content)
    monkeypatch.setattr(
        rag_ingestion,
        "parse_document",
        lambda *_: ParseResult(
            content="![diagram](images/diagram.png)",
            images={"images/diagram.png": "eA=="},
            engine="builtin",
        ),
    )
    monkeypatch.setattr(
        rag_ingestion,
        "persist_parser_images",
        lambda *_: (
            "![diagram](minio://llm-wiki/203/images/diagram.png)",
            [{"object_key": "203/images/diagram.png"}],
        ),
        raising=False,
    )
    outcome = await execute_run_message(
        created.run_id,
        worker_id="test-worker",
        handlers={"document_process": document_process_handler},
        session_factory=async_session_factory,
    )

    async with async_session_factory() as db:
        revision = await db.get(DocumentRevision, created.revision_id)
        document = await db.get(Document, created.document_id)
        chunks = (
            await db.execute(
                select(ContentChunk)
                .where(ContentChunk.revision_id == created.revision_id)
                .order_by(ContentChunk.chunk_index)
            )
        ).scalars().all()
        child_run = (
            await db.execute(
                select(ProcessingRun).where(
                    ProcessingRun.parent_run_id == created.run_id,
                    ProcessingRun.run_type == "rag_index",
                )
            )
        ).scalar_one()
        child_outbox = (
            await db.execute(select(TaskOutbox).where(TaskOutbox.run_id == child_run.id))
        ).scalar_one()

    assert outcome == ExecutionOutcome.SUCCEEDED
    assert document is not None and document.active_revision_id is None
    assert revision is not None and revision.status == "ready"
    assert revision.parse_metadata["images"] == [{"object_key": "203/images/diagram.png"}]
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert all(chunk.embedding_run_id is None for chunk in chunks)
    assert child_run.scope_id == created.revision_id
    assert child_outbox.queue_name == "llmwiki:tasks:critical"


@pytest.mark.asyncio
async def test_rag_index_activates_revision_only_after_embedding_succeeds(monkeypatch):
    """索引成功后才写 embedding 并原子激活候选 Revision。"""
    from app.parsers.core.schemas import ParseResult
    from app.parsers.service.document import create_document_process_run
    from app.workers import rag_ingestion
    from app.workers.executor import ExecutionOutcome, execute_run_message
    from app.workers.tasks import RUN_HANDLERS

    content = b"# Activation candidate\n"
    async with async_session_factory() as db:
        async with db.begin():
            db.add(Tenant(id=TEST_TENANT_ID, name="rag-index-handler-test"))
            await db.flush()
            db.add(
                KnowledgeBase(
                    id=TEST_KB_ID,
                    tenant_id=TEST_TENANT_ID,
                    name="rag-index-handler-test",
                    embedding_model="test-embedding",
                    embedding_dim=3,
                )
            )
            await db.flush()
            source = Source(
                tenant_id=TEST_TENANT_ID,
                kb_id=TEST_KB_ID,
                source_type="manual",
                name="Manual uploads",
            )
            db.add(source)
            await db.flush()
            created = await create_document_process_run(
                db,
                tenant_id=TEST_TENANT_ID,
                kb_id=TEST_KB_ID,
                source_id=source.id,
                filename="activation.md",
                content=content,
                media_type="text/markdown",
                storage_key="203/rag-index-handler/activation.md",
                parser_engine="builtin",
                requested_by_user_id=None,
            )

    monkeypatch.setattr(rag_ingestion, "get_bytes", lambda _: content)
    monkeypatch.setattr(
        rag_ingestion,
        "parse_document",
        lambda *_: ParseResult(content="candidate text", engine="builtin"),
    )
    monkeypatch.setattr(
        rag_ingestion,
        "embed_texts",
        lambda texts: [[0.1, 0.2, 0.3] for _ in texts],
        raising=False,
    )

    document_outcome = await execute_run_message(
        created.run_id,
        worker_id="test-worker",
        handlers=RUN_HANDLERS,
        session_factory=async_session_factory,
    )
    async with async_session_factory() as db:
        index_run = (
            await db.execute(
                select(ProcessingRun).where(
                    ProcessingRun.parent_run_id == created.run_id,
                    ProcessingRun.run_type == "rag_index",
                )
            )
        ).scalar_one()

    index_outcome = await execute_run_message(
        index_run.id,
        worker_id="test-worker",
        handlers=RUN_HANDLERS,
        session_factory=async_session_factory,
    )

    async with async_session_factory() as db:
        document = await db.get(Document, created.document_id)
        revision = await db.get(DocumentRevision, created.revision_id)
        chunks = (
            await db.execute(
                select(ContentChunk).where(ContentChunk.revision_id == created.revision_id)
            )
        ).scalars().all()

    assert document_outcome == ExecutionOutcome.SUCCEEDED
    assert index_outcome == ExecutionOutcome.SUCCEEDED
    assert document is not None and document.active_revision_id == created.revision_id
    assert document.status == "processed"
    assert revision is not None and revision.status == "ready"
    assert all(chunk.embedding_run_id == index_run.id for chunk in chunks)
    assert all(chunk.embedding_dim == 3 for chunk in chunks)


@pytest.mark.asyncio
async def test_rag_index_embedding_failure_keeps_old_active_revision(monkeypatch):
    """embedding 失败只能重试，不能暴露尚未索引的新版本。"""
    from app.workers import rag_ingestion
    from app.workers.broker import CRITICAL_QUEUE
    from app.workers.executor import ExecutionOutcome, execute_run_message
    from app.workers.runtime import create_run_with_outbox
    from app.workers.tasks import RUN_HANDLERS

    async with async_session_factory() as db:
        async with db.begin():
            db.add(Tenant(id=TEST_TENANT_ID, name="rag-index-failure-test"))
            await db.flush()
            kb = KnowledgeBase(
                id=TEST_KB_ID,
                tenant_id=TEST_TENANT_ID,
                name="rag-index-failure-test",
                embedding_model="test-embedding",
                embedding_dim=3,
            )
            source = Source(
                tenant_id=TEST_TENANT_ID,
                kb_id=TEST_KB_ID,
                source_type="manual",
                name="Manual uploads",
            )
            user = User(
                tenant_id=TEST_TENANT_ID,
                email="rag-index-failure@example.local",
                password_hash="not-used-by-this-test",
            )
            db.add_all([kb, source, user])
            await db.flush()
            document = Document(
                tenant_id=TEST_TENANT_ID,
                kb_id=TEST_KB_ID,
                source_id=source.id,
                source_document_key="rag-index-failure",
                title="failure.md",
                original_filename="failure.md",
                minio_key="203/rag-index-failure/old.md",
                status="processed",
                parser_engine="builtin",
            )
            db.add(document)
            await db.flush()
            active_revision = DocumentRevision(
                document_id=document.id,
                revision_no=1,
                original_filename="old.md",
                media_type="text/markdown",
                size_bytes=3,
                content_sha256="0" * 64,
                storage_key="203/rag-index-failure/old.md",
                status="ready",
            )
            candidate_revision = DocumentRevision(
                document_id=document.id,
                revision_no=2,
                original_filename="failure.md",
                media_type="text/markdown",
                size_bytes=9,
                content_sha256="1" * 64,
                storage_key="203/rag-index-failure/candidate.md",
                status="ready",
            )
            db.add_all([active_revision, candidate_revision])
            await db.flush()
            document.active_revision_id = active_revision.id
            index_run = await create_run_with_outbox(
                db,
                tenant_id=TEST_TENANT_ID,
                kb_id=TEST_KB_ID,
                run_type="rag_index",
                scope_type="revision",
                scope_id=candidate_revision.id,
                trigger_type="system",
                queue_name=CRITICAL_QUEUE,
            )
            db.add(
                ContentChunk(
                    tenant_id=TEST_TENANT_ID,
                    kb_id=TEST_KB_ID,
                    doc_id=document.doc_id,
                    source_id=source.id,
                    document_id=document.id,
                    revision_id=candidate_revision.id,
                    processing_run_id=index_run.id,
                    chunk_index=0,
                    chunk_type="document",
                    text="candidate text",
                    token_count=2,
                    text_sha256=sha256(b"candidate text").hexdigest(),
                    source_locator={},
                )
            )

    def raise_embedding_error(_: list[str]) -> list[list[float]]:
        raise ConnectionError("embedding unavailable")

    monkeypatch.setattr(rag_ingestion, "embed_texts", raise_embedding_error)
    outcome = await execute_run_message(
        index_run.id,
        worker_id="test-worker",
        handlers=RUN_HANDLERS,
        session_factory=async_session_factory,
        retry_jitter=lambda _: 0,
    )

    async with async_session_factory() as db:
        persisted_document = await db.get(Document, document.id)
        candidate_chunk = (
            await db.execute(
                select(ContentChunk).where(ContentChunk.revision_id == candidate_revision.id)
            )
        ).scalar_one()
        persisted_run = await db.get(ProcessingRun, index_run.id)
        from app.parsers.service.document import get_document_status

        status = await get_document_status(db, TEST_KB_ID, user, document.doc_id)

    assert outcome == ExecutionOutcome.RETRY_SCHEDULED
    assert persisted_document is not None
    assert persisted_document.active_revision_id == active_revision.id
    assert persisted_document.status == "processed"
    assert candidate_chunk.embedding_run_id is None
    assert persisted_run is not None and persisted_run.status == "pending"
    assert status.status == "pending"


@pytest.mark.asyncio
async def test_search_excludes_candidate_revision_chunks():
    """候选 Revision 的 chunks 在激活前不得进入在线检索。"""
    from app.search.service.search import bm25_search
    from app.workers.broker import DEFAULT_QUEUE
    from app.workers.runtime import create_run_with_outbox

    async with async_session_factory() as db:
        async with db.begin():
            db.add(Tenant(id=TEST_TENANT_ID, name="active-revision-search-test"))
            await db.flush()
            db.add(
                KnowledgeBase(
                    id=TEST_KB_ID,
                    tenant_id=TEST_TENANT_ID,
                    name="active-revision-search-test",
                    embedding_model="test-embedding",
                    embedding_dim=3,
                )
            )
            source = Source(
                tenant_id=TEST_TENANT_ID,
                kb_id=TEST_KB_ID,
                source_type="manual",
                name="Manual uploads",
            )
            db.add(source)
            await db.flush()
            document = Document(
                tenant_id=TEST_TENANT_ID,
                kb_id=TEST_KB_ID,
                source_id=source.id,
                source_document_key="active-revision-search",
                title="search.md",
                original_filename="search.md",
                minio_key="203/active-revision-search/old.md",
                status="processed",
                parser_engine="builtin",
            )
            db.add(document)
            await db.flush()
            active_revision = DocumentRevision(
                document_id=document.id,
                revision_no=1,
                original_filename="old.md",
                media_type="text/markdown",
                size_bytes=3,
                content_sha256="2" * 64,
                storage_key="203/active-revision-search/old.md",
                status="ready",
            )
            candidate_revision = DocumentRevision(
                document_id=document.id,
                revision_no=2,
                original_filename="candidate.md",
                media_type="text/markdown",
                size_bytes=9,
                content_sha256="3" * 64,
                storage_key="203/active-revision-search/candidate.md",
                status="ready",
            )
            db.add_all([active_revision, candidate_revision])
            await db.flush()
            document.active_revision_id = active_revision.id
            processing_run = await create_run_with_outbox(
                db,
                tenant_id=TEST_TENANT_ID,
                kb_id=TEST_KB_ID,
                run_type="document_process",
                scope_type="revision",
                scope_id=candidate_revision.id,
                trigger_type="system",
                queue_name=DEFAULT_QUEUE,
            )
            db.add(
                ContentChunk(
                    tenant_id=TEST_TENANT_ID,
                    kb_id=TEST_KB_ID,
                    doc_id=document.doc_id,
                    source_id=source.id,
                    document_id=document.id,
                    revision_id=candidate_revision.id,
                    processing_run_id=processing_run.id,
                    chunk_index=0,
                    chunk_type="document",
                    text="candidateleak",
                    token_count=2,
                    text_sha256=sha256(b"candidateleak").hexdigest(),
                    source_locator={},
                )
            )

    async with async_session_factory() as db:
        hits = await bm25_search(db, TEST_KB_ID, "candidateleak")

    assert hits == []
