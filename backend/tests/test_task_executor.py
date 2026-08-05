"""Dramatiq 消息到 Run 状态机的执行契约测试。

覆盖 executor.py 的 execute_run_message：claim -> handler 派发 -> commit/fail。
重试由 Dramatiq Retries middleware 接管，executor 不再调度重试。
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.models.database import async_engine, async_session_factory
from app.models.task_runtime import ProcessingRun, ProcessingSpan
from app.workers.core.constants import SpanName, SpanStatus
from app.workers.core.executor import execute_run_message
from app.workers.core.runtime import claim_run, create_run

TEST_TENANT_ID = 98_001


@pytest_asyncio.fixture(autouse=True)
async def clean_executor_rows() -> AsyncIterator[None]:
    """执行器用例会提交多会话事務，因此按专用 tenant 显式清理。"""
    await async_engine.dispose()
    async with async_session_factory() as db:
        run_ids = select(ProcessingRun.id).where(
            ProcessingRun.tenant_id == TEST_TENANT_ID
        )
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
        await db.execute(delete(ProcessingSpan).where(ProcessingSpan.run_id.in_(run_ids)))
        await db.execute(
            delete(ProcessingRun).where(ProcessingRun.tenant_id == TEST_TENANT_ID)
        )
        await db.commit()
    await async_engine.dispose()


async def _create_run(*, run_type: str = "document_process") -> int:
    """创建一个 pending 状态的 Run 并返回其 id。"""
    async with async_session_factory() as db:
        async with db.begin():
            run = await create_run(
                db,
                tenant_id=TEST_TENANT_ID,
                kb_id=202,
                run_type=run_type,
                scope_type="revision",
                scope_id=303,
                trigger_type="manual",
            )
        return run.id


async def _load_run(run_id: int) -> ProcessingRun:
    async with async_session_factory() as db:
        run = await db.get(ProcessingRun, run_id)
        assert run is not None
        return run


@pytest.mark.asyncio
async def test_duplicate_message_does_not_run_handler():
    """重复投递的消息被 claim_run 吸收，handler 不执行。"""
    run_id = await _create_run()
    async with async_session_factory() as db:
        async with db.begin():
            # 先用外部 claim_run 把 Run 领走（模拟另一 worker 已在处理）
            await claim_run(db, run_id, worker_id="worker-a")

    called = False

    async def handler(context):
        nonlocal called
        called = True

    from app.workers.core.schemas import ExecutionOutcome

    outcome = await execute_run_message(
        run_id,
        worker_id="worker-b",
        handlers={"document_process": handler},
        session_factory=async_session_factory,
    )
    assert outcome == ExecutionOutcome.IGNORED
    assert not called


@pytest.mark.asyncio
async def test_successful_handler_atomically_completes_run():
    """handler 调 commit_success 后 Run 原子转为 succeeded。"""
    from app.workers.core.schemas import ExecutionOutcome

    run_id = await _create_run()

    async def handler(context):
        await context.commit_success()

    outcome = await execute_run_message(
        run_id,
        worker_id="worker-a",
        handlers={"document_process": handler},
        session_factory=async_session_factory,
    )
    assert outcome == ExecutionOutcome.SUCCEEDED
    run = await _load_run(run_id)
    assert run.status == "succeeded"


@pytest.mark.asyncio
async def test_terminal_error_marks_run_failed():
    """handler 抛 TerminalTaskError 后 Run 标记为 failed，不重试。"""
    from app.workers.core.errors import TerminalTaskError
    from app.workers.core.schemas import ExecutionOutcome

    run_id = await _create_run(run_type="rag_index")

    async def handler(context):
        raise TerminalTaskError("invalid_embedding", "wrong dimension")

    outcome = await execute_run_message(
        run_id,
        worker_id="worker-a",
        handlers={"rag_index": handler},
        session_factory=async_session_factory,
    )
    assert outcome == ExecutionOutcome.FAILED
    run = await _load_run(run_id)
    assert run.status == "failed"
    assert run.error_code == "invalid_embedding"
    assert run.error_message == "wrong dimension"


@pytest.mark.asyncio
async def test_transient_error_marks_run_failed():
    """handler 抛非 Terminal 异常时包装为 TransientTaskError，Run 标 failed。

    注意：当前重试语义为已知限制，Run 直接进 failed（Dramatiq 重试会被 claim_run 吸收）。
    """
    from app.workers.core.schemas import ExecutionOutcome

    run_id = await _create_run()

    async def handler(context):
        raise ConnectionError("embedding unavailable")

    outcome = await execute_run_message(
        run_id,
        worker_id="worker-a",
        handlers={"document_process": handler},
        session_factory=async_session_factory,
    )
    assert outcome == ExecutionOutcome.FAILED
    run = await _load_run(run_id)
    assert run.status == "failed"
    assert run.error_code == "unexpected_exception"


@pytest.mark.asyncio
async def test_handler_without_commit_raises_terminal_error():
    """handler 返回但未调 commit_success 时标记为契约违反。"""
    from app.workers.core.schemas import ExecutionOutcome

    run_id = await _create_run()

    async def handler(context):
        pass  # 忘记调 commit_success

    outcome = await execute_run_message(
        run_id,
        worker_id="worker-a",
        handlers={"document_process": handler},
        session_factory=async_session_factory,
    )
    assert outcome == ExecutionOutcome.FAILED
    run = await _load_run(run_id)
    assert run.status == "failed"
    assert run.error_code == "handler_contract_violation"


@pytest.mark.asyncio
async def test_cancelled_handler_marks_span_cancelled():
    """CancelledError（time_limit 触发）标记 span cancelled，异常冒泡。"""
    import asyncio

    run_id = await _create_run()

    async def handler(context):
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await execute_run_message(
            run_id,
            worker_id="worker-a",
            handlers={"document_process": handler},
            session_factory=async_session_factory,
        )
    # Run 仍是 running（_handle_failure 未调用），Reaper 后续兜底
    run = await _load_run(run_id)
    assert run.status == "running"
    async with async_session_factory() as db:
        attempt = (
            await db.execute(
                select(ProcessingSpan)
                .where(
                    ProcessingSpan.run_id == run_id,
                    ProcessingSpan.span_name == SpanName.WORKER_ATTEMPT,
                )
                .order_by(ProcessingSpan.id.desc())
                .limit(1)
            )
        ).scalar_one()
    assert attempt.status == SpanStatus.CANCELLED


@pytest.mark.asyncio
async def test_unknown_run_type_raises_terminal_error():
    """未注册的 run_type 标记为 unknown_run_type。"""
    from app.workers.core.schemas import ExecutionOutcome

    run_id = await _create_run(run_type="unknown_type")

    async def handler(context):
        await context.commit_success()

    outcome = await execute_run_message(
        run_id,
        worker_id="worker-a",
        handlers={"document_process": handler},
        session_factory=async_session_factory,
    )
    assert outcome == ExecutionOutcome.FAILED
    run = await _load_run(run_id)
    assert run.status == "failed"
    assert run.error_code == "unknown_run_type"


@pytest.mark.asyncio
async def test_nonexistent_run_returns_ignored():
    """不存在的 run_id 返回 IGNORED，不抛异常。"""
    from app.workers.core.schemas import ExecutionOutcome

    outcome = await execute_run_message(
        999999,
        worker_id="worker-a",
        handlers={},
        session_factory=async_session_factory,
    )
    assert outcome == ExecutionOutcome.IGNORED
