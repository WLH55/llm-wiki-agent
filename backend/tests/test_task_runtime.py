"""Dramatiq 任务运行账本与状态机的 PostgreSQL 契约测试。

覆盖 runtime.py 的 create_run / claim_run / complete_run / fail_run /
mark_run_enqueue_failed / start_worker_attempt / finish_worker_attempt，
以及 reaper.py 的 recover_stalled_runs。
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import async_engine
from app.models.task_runtime import ProcessingSpan
from app.workers.core.constants import ErrorCode, RunStatus, SpanName, SpanStatus
from app.workers.core.reaper import recover_stalled_runs
from app.workers.core.runtime import (
    claim_run,
    complete_run,
    create_run,
    fail_run,
    finish_worker_attempt,
    mark_run_enqueue_failed,
    start_worker_attempt,
)


@pytest_asyncio.fixture
async def runtime_session() -> AsyncSession:
    """每个用例运行在独立事务中，结束后回滚测试数据。"""
    await async_engine.dispose()
    async with async_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(bind=connection, expire_on_commit=False)
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await async_engine.dispose()


@pytest.mark.asyncio
async def test_create_run_persists_pending_run(runtime_session: AsyncSession):
    """create_run 在调用方事务中写入 pending 状态的 Run 行。"""
    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=303,
        trigger_type="manual",
    )
    await runtime_session.flush()
    assert run.status == RunStatus.PENDING
    assert run.run_type == "document_process"
    assert run.attempt_no == 1
    assert run.options_snapshot == {}


@pytest.mark.asyncio
async def test_claim_run_transitions_pending_to_running(runtime_session: AsyncSession):
    """claim_run 通过 CAS pending->running 领取 Run，重复领取返回 False。"""
    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=304,
        trigger_type="manual",
    )
    await runtime_session.flush()
    first = await claim_run(runtime_session, run.id, worker_id="worker-a")
    second = await claim_run(runtime_session, run.id, worker_id="worker-b")
    assert first is True
    assert second is False
    await runtime_session.refresh(run)
    assert run.status == RunStatus.RUNNING


@pytest.mark.asyncio
async def test_complete_run_transitions_running_to_succeeded(runtime_session: AsyncSession):
    """complete_run 通过 CAS running->succeeded 完成_run，非 running 状态返回 False。"""
    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=305,
        trigger_type="manual",
    )
    await runtime_session.flush()
    await claim_run(runtime_session, run.id, worker_id="worker-a")
    assert await complete_run(runtime_session, run.id) is True
    assert await complete_run(runtime_session, run.id) is False
    await runtime_session.refresh(run)
    assert run.status == RunStatus.SUCCEEDED


@pytest.mark.asyncio
async def test_fail_run_transitions_running_to_failed(runtime_session: AsyncSession):
    """fail_run 通过 CAS running->failed 标记失败，记录错误码与摘要。"""
    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="rag_index",
        scope_type="revision",
        scope_id=306,
        trigger_type="on_ingest",
    )
    await runtime_session.flush()
    await claim_run(runtime_session, run.id, worker_id="worker-a")
    assert await fail_run(
        runtime_session,
        run.id,
        error_code="embedding_invalid",
        error_message="invalid vector",
    ) is True
    await runtime_session.refresh(run)
    assert run.status == RunStatus.FAILED
    assert run.error_code == "embedding_invalid"
    assert run.error_message == "invalid vector"


@pytest.mark.asyncio
async def test_fail_run_rejects_non_running_run(runtime_session: AsyncSession):
    """fail_run 对 pending Run 返回 False（CAS 条件不满足）。"""
    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=307,
        trigger_type="manual",
    )
    await runtime_session.flush()
    assert await fail_run(
        runtime_session,
        run.id,
        error_code="test_error",
        error_message="should not apply",
    ) is False
    await runtime_session.refresh(run)
    assert run.status == RunStatus.PENDING


@pytest.mark.asyncio
async def test_mark_run_enqueue_failed_transitions_pending_to_failed(
    runtime_session: AsyncSession,
):
    """mark_run_enqueue_failed 将卡在 pending 的 Run 标为 failed（入队失败场景）。"""
    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=308,
        trigger_type="manual",
    )
    await runtime_session.flush()
    await mark_run_enqueue_failed(
        runtime_session,
        run.id,
        error_message="redis unavailable",
    )
    await runtime_session.refresh(run)
    assert run.status == RunStatus.FAILED
    assert run.error_code == ErrorCode.ENQUEUE_FAILED
    assert "redis unavailable" in (run.error_message or "")


@pytest.mark.asyncio
async def test_start_worker_attempt_creates_running_span(runtime_session: AsyncSession):
    """start_worker_attempt 为每次执行创建 running 状态的 worker_attempt span。"""
    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=309,
        trigger_type="manual",
    )
    await runtime_session.flush()
    await claim_run(runtime_session, run.id, worker_id="worker-a")
    span = await start_worker_attempt(runtime_session, run, worker_id="worker-a")
    assert span.span_name == SpanName.WORKER_ATTEMPT
    assert span.status == SpanStatus.RUNNING
    assert span.metrics["attempt"] == 1
    assert span.metrics["worker_id"] == "worker-a"


@pytest.mark.asyncio
async def test_finish_worker_attempt_transitions_to_failed(runtime_session: AsyncSession):
    """finish_worker_attempt 将 span 从 running 标记为 failed，记录错误信息。"""
    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=310,
        trigger_type="manual",
    )
    await runtime_session.flush()
    await claim_run(runtime_session, run.id, worker_id="worker-a")
    span = await start_worker_attempt(runtime_session, run, worker_id="worker-a")
    assert await finish_worker_attempt(
        runtime_session,
        span.id,
        status=SpanStatus.FAILED,
        error_code="temporary_failure",
        error_message="retrying",
    ) is True
    await runtime_session.refresh(span)
    assert span.status == SpanStatus.FAILED
    assert span.error_code == "temporary_failure"


@pytest.mark.asyncio
async def test_finish_worker_attempt_rejects_invalid_status(runtime_session: AsyncSession):
    """finish_worker_attempt 只接受 succeeded/failed/cancelled 三种终态。"""
    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=311,
        trigger_type="manual",
    )
    await runtime_session.flush()
    await claim_run(runtime_session, run.id, worker_id="worker-a")
    span = await start_worker_attempt(runtime_session, run, worker_id="worker-a")
    with pytest.raises(ValueError, match="invalid worker attempt status"):
        await finish_worker_attempt(runtime_session, span.id, status="running")


@pytest.mark.asyncio
async def test_second_attempt_creates_new_span_with_incremented_attempt(
    runtime_session: AsyncSession,
):
    """多次 start_worker_attempt 创建独立 span，attempt 序号递增。"""
    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=312,
        trigger_type="manual",
    )
    await runtime_session.flush()
    await claim_run(runtime_session, run.id, worker_id="worker-a")
    first = await start_worker_attempt(runtime_session, run, worker_id="worker-a")
    await finish_worker_attempt(runtime_session, first.id, status=SpanStatus.FAILED)
    second = await start_worker_attempt(runtime_session, run, worker_id="worker-b")
    assert first.metrics["attempt"] == 1
    assert second.metrics["attempt"] == 2
    spans = (
        await runtime_session.execute(
            select(ProcessingSpan)
            .where(
                ProcessingSpan.run_id == run.id,
                ProcessingSpan.span_name == SpanName.WORKER_ATTEMPT,
            )
            .order_by(ProcessingSpan.id)
        )
    ).scalars().all()
    assert [s.status for s in spans] == [SpanStatus.FAILED, SpanStatus.RUNNING]


@pytest.mark.asyncio
async def test_reaper_recovers_running_run_with_stale_span(runtime_session: AsyncSession):
    """recover_stalled_runs 标记 span 心跳超时的 running Run 为 failed。"""
    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=313,
        trigger_type="manual",
    )
    await runtime_session.flush()
    await claim_run(runtime_session, run.id, worker_id="worker-a")
    span = await start_worker_attempt(runtime_session, run, worker_id="worker-a")
    # 模拟 span 心跳超时：把 started_at 和 updated_at 回拨到很久以前
    from datetime import datetime, timedelta, timezone

    old_time = datetime.now(timezone.utc) - timedelta(hours=2)
    span.started_at = old_time
    span.updated_at = old_time
    run.started_at = old_time
    await runtime_session.flush()

    recovered = await recover_stalled_runs(
        runtime_session,
        span_stale_seconds=4200,
        pending_stale_seconds=300,
    )
    assert run.id in recovered
    await runtime_session.refresh(run)
    assert run.status == RunStatus.FAILED
    assert run.error_code == ErrorCode.REAPER_RECOVERED


@pytest.mark.asyncio
async def test_reaper_recovers_stale_pending_run(runtime_session: AsyncSession):
    """recover_stalled_runs 标记入队失败卡 pending 的 Run 为 failed。"""
    from datetime import datetime, timedelta, timezone

    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=314,
        trigger_type="manual",
    )
    await runtime_session.flush()
    # 模拟 pending 过旧：把 created_at 回拨到很久以前
    run.created_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await runtime_session.flush()

    recovered = await recover_stalled_runs(
        runtime_session,
        span_stale_seconds=4200,
        pending_stale_seconds=300,
    )
    assert run.id in recovered
    await runtime_session.refresh(run)
    assert run.status == RunStatus.FAILED
    assert run.error_code == ErrorCode.REAPER_RECOVERED


@pytest.mark.asyncio
async def test_reaper_skips_fresh_running_run(runtime_session: AsyncSession):
    """recover_stalled_runs 不误杀刚启动的 running Run（span 心跳未超时）。"""
    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=315,
        trigger_type="manual",
    )
    await runtime_session.flush()
    await claim_run(runtime_session, run.id, worker_id="worker-a")
    await start_worker_attempt(runtime_session, run, worker_id="worker-a")
    await runtime_session.flush()

    recovered = await recover_stalled_runs(
        runtime_session,
        span_stale_seconds=4200,
        pending_stale_seconds=300,
    )
    assert recovered == []
    await runtime_session.refresh(run)
    assert run.status == RunStatus.RUNNING


@pytest.mark.asyncio
async def test_reaper_skips_succeeded_run(runtime_session: AsyncSession):
    """recover_stalled_runs 通过 CAS status IN (running, pending) 跳过已终态的 Run。"""
    from datetime import datetime, timedelta, timezone

    run = await create_run(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=316,
        trigger_type="manual",
    )
    await runtime_session.flush()
    await claim_run(runtime_session, run.id, worker_id="worker-a")
    await complete_run(runtime_session, run.id)
    # 即使时间回拨，CAS 也不会命中 succeeded Run
    run.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
    await runtime_session.flush()

    recovered = await recover_stalled_runs(
        runtime_session,
        span_stale_seconds=4200,
        pending_stale_seconds=300,
    )
    assert recovered == []
    await runtime_session.refresh(run)
    assert run.status == RunStatus.SUCCEEDED
