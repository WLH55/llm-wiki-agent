"""Taskiq 消息到 PostgreSQL Run 状态机的执行契约测试。"""

import asyncio
import importlib
import importlib.util
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.models.database import async_engine, async_session_factory
from app.models.task_runtime import ProcessingRun, ProcessingSpan, TaskOutbox
from app.workers.core.runtime import claim_run, create_run_with_outbox

TEST_TENANT_ID = 98_001


def _executor_module():
    spec = importlib.util.find_spec("app.workers.core.executor")
    assert spec is not None, "app.workers.core.executor must exist"
    return importlib.import_module("app.workers.core.executor")


@pytest_asyncio.fixture(autouse=True)
async def clean_executor_rows() -> AsyncIterator[None]:
    """执行器用例会提交多会话事务，因此按专用 tenant 显式清理。"""
    await async_engine.dispose()
    async with async_session_factory() as db:
        run_ids = select(ProcessingRun.id).where(
            ProcessingRun.tenant_id == TEST_TENANT_ID
        )
        await db.execute(delete(TaskOutbox).where(TaskOutbox.run_id.in_(run_ids)))
        await db.execute(delete(ProcessingSpan).where(ProcessingSpan.run_id.in_(run_ids)))
        await db.execute(
            delete(ProcessingRun).where(ProcessingRun.tenant_id == TEST_TENANT_ID)
        )
        await db.commit()
    yield
    async with async_session_factory() as db:
        run_ids = select(ProcessingRun.id).where(
            ProcessingRun.tenant_id == TEST_TENANT_ID
        )
        await db.execute(delete(TaskOutbox).where(TaskOutbox.run_id.in_(run_ids)))
        await db.execute(delete(ProcessingSpan).where(ProcessingSpan.run_id.in_(run_ids)))
        await db.execute(
            delete(ProcessingRun).where(ProcessingRun.tenant_id == TEST_TENANT_ID)
        )
        await db.commit()
    await async_engine.dispose()


async def _create_run(*, run_type: str = "document_process") -> int:
    async with async_session_factory() as db:
        async with db.begin():
            run = await create_run_with_outbox(
                db,
                tenant_id=TEST_TENANT_ID,
                kb_id=202,
                run_type=run_type,
                scope_type="revision",
                scope_id=303,
                trigger_type="manual",
                queue_name="default",
            )
        return run.id


async def _load_run(run_id: int) -> ProcessingRun:
    async with async_session_factory() as db:
        run = await db.get(ProcessingRun, run_id)
        assert run is not None
        return run


@pytest.mark.asyncio
async def test_duplicate_message_with_active_lease_does_not_run_handler():
    executor = _executor_module()
    run_id = await _create_run()
    async with async_session_factory() as db:
        async with db.begin():
            lease = await claim_run(
                db,
                run_id,
                worker_id="worker-a",
                lease_seconds=60,
            )
            assert lease is not None

    called = False

    async def handler(context):
        nonlocal called
        called = True

    outcome = await executor.execute_run_message(
        run_id,
        worker_id="worker-b",
        handlers={"document_process": handler},
        session_factory=async_session_factory,
    )
    assert outcome == executor.ExecutionOutcome.IGNORED
    assert not called


@pytest.mark.asyncio
async def test_successful_handler_atomically_completes_run():
    executor = _executor_module()
    run_id = await _create_run()

    async def handler(context):
        await context.commit_success()

    outcome = await executor.execute_run_message(
        run_id,
        worker_id="worker-a",
        handlers={"document_process": handler},
        session_factory=async_session_factory,
    )
    assert outcome == executor.ExecutionOutcome.SUCCEEDED
    run = await _load_run(run_id)
    assert run.status == "succeeded"
    assert run.execution_token is None


@pytest.mark.asyncio
async def test_transient_error_schedules_same_run_retry():
    executor = _executor_module()
    run_id = await _create_run()

    async def handler(context):
        raise executor.TransientTaskError("embedding_unavailable", "provider down")

    outcome = await executor.execute_run_message(
        run_id,
        worker_id="worker-a",
        handlers={"document_process": handler},
        session_factory=async_session_factory,
        retry_base_seconds=0,
        retry_jitter=lambda delay: 0,
    )
    assert outcome == executor.ExecutionOutcome.RETRY_SCHEDULED
    run = await _load_run(run_id)
    assert run.status == "pending"
    async with async_session_factory() as db:
        outboxes = (
            await db.execute(
                select(TaskOutbox)
                .where(TaskOutbox.run_id == run_id)
                .order_by(TaskOutbox.id)
            )
        ).scalars().all()
    assert len(outboxes) == 2
    assert outboxes[-1].last_error == "embedding_unavailable"


@pytest.mark.asyncio
async def test_terminal_error_marks_run_failed_without_retry():
    executor = _executor_module()
    run_id = await _create_run(run_type="rag_index")

    async def handler(context):
        raise executor.TerminalTaskError("invalid_embedding", "wrong dimension")

    outcome = await executor.execute_run_message(
        run_id,
        worker_id="worker-a",
        handlers={"rag_index": handler},
        session_factory=async_session_factory,
    )
    assert outcome == executor.ExecutionOutcome.FAILED
    run = await _load_run(run_id)
    assert run.status == "failed"
    assert run.error_code == "invalid_embedding"


@pytest.mark.asyncio
async def test_heartbeat_keeps_short_lease_alive_for_long_handler():
    executor = _executor_module()
    run_id = await _create_run()

    async def handler(context):
        await asyncio.sleep(0.18)
        await context.commit_success()

    outcome = await executor.execute_run_message(
        run_id,
        worker_id="worker-a",
        handlers={"document_process": handler},
        session_factory=async_session_factory,
        lease_seconds=0.09,
        heartbeat_seconds=0.02,
    )
    assert outcome == executor.ExecutionOutcome.SUCCEEDED


@pytest.mark.asyncio
async def test_cancelled_handler_propagates_and_leaves_run_for_lease_recovery():
    executor = _executor_module()
    run_id = await _create_run()

    async def handler(context):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await executor.execute_run_message(
            run_id,
            worker_id="worker-a",
            handlers={"document_process": handler},
            session_factory=async_session_factory,
            lease_seconds=60,
        )
    run = await _load_run(run_id)
    assert run.status == "running"
    assert run.execution_token is not None
    async with async_session_factory() as db:
        attempt = (
            await db.execute(
                select(ProcessingSpan)
                .where(
                    ProcessingSpan.run_id == run_id,
                    ProcessingSpan.span_name == "worker_attempt",
                )
                .order_by(ProcessingSpan.id.desc())
                .limit(1)
            )
        ).scalar_one()
    assert attempt.status == "cancelled"
