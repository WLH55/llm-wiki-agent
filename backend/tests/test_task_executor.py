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
from app.workers.core.constants import ErrorCode, SpanName, SpanStatus
from app.workers.core.executor import execute_run_message
from app.workers.core.runtime import claim_run, create_run, release_run

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
            await claim_run(db, run_id)

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
async def test_terminal_error_propagates_and_run_stays_running():
    """handler 抛 TerminalTaskError：span 标 failed、Run 保持 running，异常冒泡。

    终态标记由 RunFailureMiddleware 在消息死亡时完成（throws -> DLQ）。
    """
    from app.workers.core.errors import TerminalTaskError

    run_id = await _create_run(run_type="rag_index")

    async def handler(context):
        raise TerminalTaskError("invalid_embedding", "wrong dimension")

    with pytest.raises(TerminalTaskError):
        await execute_run_message(
            run_id,
            worker_id="worker-a",
            handlers={"rag_index": handler},
            session_factory=async_session_factory,
        )
    run = await _load_run(run_id)
    assert run.status == "running"
    assert run.error_code is None
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
    assert attempt.status == SpanStatus.FAILED
    assert attempt.error_code == "invalid_embedding"


@pytest.mark.asyncio
async def test_transient_error_releases_run_and_propagates():
    """handler 抛非 Terminal 异常：包装为 TransientTaskError、span 标 failed、
    Run 回 pending（重投消息可再次 claim），异常冒泡给 Retries 退避重试。
    """
    from app.workers.core.errors import TransientTaskError

    run_id = await _create_run()

    async def handler(context):
        raise ConnectionError("embedding unavailable")

    with pytest.raises(TransientTaskError):
        await execute_run_message(
            run_id,
            worker_id="worker-a",
            handlers={"document_process": handler},
            session_factory=async_session_factory,
        )
    run = await _load_run(run_id)
    assert run.status == "pending"
    assert run.error_code is None
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
    assert attempt.status == SpanStatus.FAILED
    assert attempt.error_code == "unexpected_exception"


@pytest.mark.asyncio
async def test_handler_without_commit_raises_terminal_error():
    """handler 返回但未调 commit_success 时标记为契约违反（Terminal，异常冒泡）。"""
    from app.workers.core.errors import TerminalTaskError

    run_id = await _create_run()

    async def handler(context):
        pass  # 忘记调 commit_success

    with pytest.raises(TerminalTaskError):
        await execute_run_message(
            run_id,
            worker_id="worker-a",
            handlers={"document_process": handler},
            session_factory=async_session_factory,
        )
    run = await _load_run(run_id)
    assert run.status == "running"


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
    # Run 保持 running（executor 不标终态），Reaper 后续兜底
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
    """未注册的 run_type 标记为 unknown_run_type（Terminal，异常冒泡）。"""
    from app.workers.core.errors import TerminalTaskError

    run_id = await _create_run(run_type="unknown_type")

    async def handler(context):
        await context.commit_success()

    with pytest.raises(TerminalTaskError):
        await execute_run_message(
            run_id,
            worker_id="worker-a",
            handlers={"document_process": handler},
            session_factory=async_session_factory,
        )
    run = await _load_run(run_id)
    assert run.status == "running"


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

@pytest.mark.asyncio
async def test_run_failure_middleware_skips_when_retry_scheduled(monkeypatch):
    """message.failed=False（Retries 已安排重试）时 RunFailureMiddleware 不标 failed。"""
    from types import SimpleNamespace

    from app.workers.core import middleware as middleware_module
    from app.workers.core.middleware import RunFailureMiddleware

    run_id = await _create_run()
    mw = RunFailureMiddleware(session_factory=async_session_factory)
    calls = []
    monkeypatch.setattr(
        middleware_module, "_run_coroutine_safely", lambda coro: calls.append(coro)
    )
    mw.after_process_message(
        None, SimpleNamespace(args=[run_id], failed=False), exception=ValueError("boom")
    )
    assert calls == []
    run = await _load_run(run_id)
    assert run.status == "pending"


@pytest.mark.asyncio
async def test_run_failure_middleware_marks_failed_when_message_dead(monkeypatch):
    """message.failed=True（throws / 重试耗尽）时 RunFailureMiddleware 标 Run failed。"""
    from types import SimpleNamespace

    from app.workers.core import middleware as middleware_module
    from app.workers.core.middleware import RunFailureMiddleware

    run_id = await _create_run()
    async with async_session_factory() as db:
        async with db.begin():
            await claim_run(db, run_id)
            await release_run(db, run_id)  # 模拟瞬态失败已释放 -> pending

    mw = RunFailureMiddleware(session_factory=async_session_factory)
    calls = []
    monkeypatch.setattr(
        middleware_module, "_run_coroutine_safely", lambda coro: (calls.append(coro), coro.close())
    )
    mw.after_process_message(
        None, SimpleNamespace(args=[run_id], failed=True), exception=ValueError("boom")
    )
    assert len(calls) == 1
    # 直接执行标记逻辑验证 DB 效果（pending -> failed）
    await mw._mark_failed(run_id, "boom")
    run = await _load_run(run_id)
    assert run.status == "failed"
    assert run.error_code == ErrorCode.MIDDLEWARE_FAILURE
    assert run.error_message == "boom"


@pytest.mark.asyncio
async def test_run_failure_middleware_mark_failed_covers_running_state():
    """终态标记覆盖 running 状态（throws 终态错误路径：executor 不 release）。"""
    from app.workers.core.middleware import RunFailureMiddleware

    run_id = await _create_run(run_type="rag_index")
    async with async_session_factory() as db:
        async with db.begin():
            await claim_run(db, run_id)

    mw = RunFailureMiddleware(session_factory=async_session_factory)
    await mw._mark_failed(run_id, "terminal boom")
    run = await _load_run(run_id)
    assert run.status == "failed"
    assert run.error_code == ErrorCode.MIDDLEWARE_FAILURE
