"""Taskiq 任务运行账本、Outbox 与执行 fencing 的 PostgreSQL 契约测试。"""

import importlib
import importlib.util
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import async_engine
from app.models.task_runtime import ProcessingRun, ProcessingSpan, TaskOutbox
from app.workers.core.runtime import (
    claim_run,
    complete_run,
    create_run_with_outbox,
    retry_run,
)
from app.workers.outbox.outbox import (
    claim_outbox_batch,
    mark_outbox_published,
    release_outbox_claim,
)
from app.workers.outbox.publisher import publish_outbox_claim
from app.workers.core import runtime as task_runtime


def _reaper_module():
    spec = importlib.util.find_spec("app.workers.outbox.reaper")
    assert spec is not None, "app.workers.outbox.reaper must exist"
    return importlib.import_module("app.workers.outbox.reaper")


@pytest_asyncio.fixture
async def runtime_session() -> AsyncSession:
    """每个用例运行在独立事务中，结束后回滚测试数据。"""
    # pytest-asyncio 为函数创建独立 loop，先清空上一个 loop 绑定的连接池。
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
async def test_create_run_and_outbox_share_one_transaction(runtime_session: AsyncSession):
    run = await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=303,
        trigger_type="manual",
        queue_name="default",
    )
    await runtime_session.flush()
    outbox = (
        await runtime_session.execute(
            select(TaskOutbox).where(TaskOutbox.run_id == run.id)
        )
    ).scalar_one()
    assert isinstance(run, ProcessingRun)
    assert outbox is not None
    assert outbox.run_id == run.id
    assert outbox.task_name == "process_run"
    assert outbox.queue_name == "default"
    assert outbox.published_at is None


@pytest.mark.asyncio
async def test_only_one_worker_can_claim_pending_run(runtime_session: AsyncSession):
    run = await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=304,
        trigger_type="manual",
        queue_name="default",
    )
    await runtime_session.flush()
    now = datetime.now(timezone.utc)
    first = await claim_run(
        runtime_session,
        run.id,
        worker_id="worker-a",
        lease_seconds=60,
        now=now,
    )
    second = await claim_run(
        runtime_session,
        run.id,
        worker_id="worker-b",
        lease_seconds=60,
        now=now,
    )
    assert first is not None
    assert first.epoch == 1
    assert second is None


@pytest.mark.asyncio
async def test_expired_lease_takeover_fences_old_worker(runtime_session: AsyncSession):
    run = await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=305,
        trigger_type="manual",
        queue_name="default",
    )
    await runtime_session.flush()
    start = datetime.now(timezone.utc)
    old_lease = await claim_run(
        runtime_session,
        run.id,
        worker_id="worker-a",
        lease_seconds=10,
        now=start,
    )
    assert old_lease is not None
    new_lease = await claim_run(
        runtime_session,
        run.id,
        worker_id="worker-b",
        lease_seconds=10,
        now=start + timedelta(seconds=11),
    )
    assert new_lease is not None
    assert new_lease.epoch == old_lease.epoch + 1
    assert not await complete_run(
        runtime_session,
        old_lease,
        now=start + timedelta(seconds=12),
    )
    assert await complete_run(
        runtime_session,
        new_lease,
        now=start + timedelta(seconds=12),
    )


@pytest.mark.asyncio
async def test_retry_reuses_run_and_creates_delayed_outbox(runtime_session: AsyncSession):
    run = await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="rag_index",
        scope_type="revision",
        scope_id=306,
        trigger_type="on_ingest",
        queue_name="critical",
    )
    await runtime_session.flush()
    now = datetime.now(timezone.utc)
    lease = await claim_run(
        runtime_session,
        run.id,
        worker_id="worker-a",
        lease_seconds=60,
        now=now,
    )
    assert lease is not None
    available_at = now + timedelta(seconds=30)
    assert await retry_run(
        runtime_session,
        lease,
        queue_name="critical",
        available_at=available_at,
        error_code="embedding_unavailable",
        now=now,
    )
    await runtime_session.flush()
    assert run.status == "pending"
    assert run.execution_token is None
    retry_outbox = (
        await runtime_session.execute(
            select(TaskOutbox)
            .where(TaskOutbox.run_id == run.id)
            .order_by(TaskOutbox.id.desc())
            .limit(1)
        )
    ).scalar_one()
    assert retry_outbox.run_id == run.id
    assert retry_outbox.available_at == available_at


@pytest.mark.asyncio
async def test_outbox_claim_is_exclusive_until_lock_expires(runtime_session: AsyncSession):
    run = await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=307,
        trigger_type="manual",
        queue_name="default",
    )
    await runtime_session.flush()
    now = datetime.now(timezone.utc)
    first = await claim_outbox_batch(
        runtime_session,
        batch_size=10,
        lock_seconds=30,
        now=now,
    )
    second = await claim_outbox_batch(
        runtime_session,
        batch_size=10,
        lock_seconds=30,
        now=now,
    )
    assert [claim.run_id for claim in first] == [run.id]
    assert second == []


@pytest.mark.asyncio
async def test_only_claim_owner_can_mark_outbox_published(runtime_session: AsyncSession):
    await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=308,
        trigger_type="manual",
        queue_name="default",
    )
    await runtime_session.flush()
    now = datetime.now(timezone.utc)
    claim = (
        await claim_outbox_batch(
            runtime_session,
            batch_size=1,
            lock_seconds=30,
            now=now,
        )
    )[0]
    wrong_claim = claim.with_lock_token("00000000-0000-0000-0000-000000000000")
    assert not await mark_outbox_published(runtime_session, wrong_claim, now=now)
    assert await mark_outbox_published(runtime_session, claim, now=now)


@pytest.mark.asyncio
async def test_publish_failure_releases_claim_with_delay(runtime_session: AsyncSession):
    await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=309,
        trigger_type="manual",
        queue_name="default",
    )
    await runtime_session.flush()
    now = datetime.now(timezone.utc)
    claim = (
        await claim_outbox_batch(
            runtime_session,
            batch_size=1,
            lock_seconds=30,
            now=now,
        )
    )[0]
    retry_at = now + timedelta(seconds=15)
    assert await release_outbox_claim(
        runtime_session,
        claim,
        error="redis unavailable",
        retry_at=retry_at,
        now=now,
    )
    await runtime_session.flush()
    outbox = await runtime_session.get(TaskOutbox, claim.outbox_id)
    assert outbox is not None
    assert outbox.publish_attempts == 1
    assert outbox.lock_token is None
    assert outbox.available_at == retry_at


@pytest.mark.asyncio
async def test_publisher_sends_identity_only_and_confirms_outbox(runtime_session: AsyncSession):
    run = await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=310,
        trigger_type="manual",
        queue_name="default",
    )
    await runtime_session.flush()
    now = datetime.now(timezone.utc)
    claim = (
        await claim_outbox_batch(
            runtime_session,
            batch_size=1,
            lock_seconds=30,
            now=now,
        )
    )[0]
    sent: list[tuple[str, int, str]] = []

    async def sender(task_name: str, run_id: int, queue_name: str) -> None:
        sent.append((task_name, run_id, queue_name))

    assert await publish_outbox_claim(
        runtime_session,
        claim,
        sender=sender,
        now=now,
    )
    assert sent == [("process_run", run.id, "default")]
    outbox = await runtime_session.get(TaskOutbox, claim.outbox_id)
    assert outbox is not None
    assert outbox.published_at == now


@pytest.mark.asyncio
async def test_publisher_failure_keeps_outbox_for_retry(runtime_session: AsyncSession):
    await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=311,
        trigger_type="manual",
        queue_name="default",
    )
    await runtime_session.flush()
    now = datetime.now(timezone.utc)
    claim = (
        await claim_outbox_batch(
            runtime_session,
            batch_size=1,
            lock_seconds=30,
            now=now,
        )
    )[0]

    async def failing_sender(task_name: str, run_id: int, queue_name: str) -> None:
        raise ConnectionError("redis unavailable")

    assert not await publish_outbox_claim(
        runtime_session,
        claim,
        sender=failing_sender,
        now=now,
        retry_delay_seconds=15,
    )
    outbox = await runtime_session.get(TaskOutbox, claim.outbox_id)
    assert outbox is not None
    assert outbox.published_at is None
    assert outbox.publish_attempts == 1
    assert outbox.available_at == now + timedelta(seconds=15)


@pytest.mark.asyncio
async def test_only_current_worker_can_renew_execution_lease(
    runtime_session: AsyncSession,
):
    renew_lease = getattr(task_runtime, "renew_lease", None)
    assert callable(renew_lease), "runtime must expose renew_lease"

    run = await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=312,
        trigger_type="manual",
        queue_name="default",
    )
    await runtime_session.flush()
    start = datetime.now(timezone.utc)
    old_lease = await claim_run(
        runtime_session,
        run.id,
        worker_id="worker-a",
        lease_seconds=10,
        now=start,
    )
    assert old_lease is not None
    current_lease = await claim_run(
        runtime_session,
        run.id,
        worker_id="worker-b",
        lease_seconds=30,
        now=start + timedelta(seconds=11),
    )
    assert current_lease is not None

    assert not await renew_lease(
        runtime_session,
        old_lease,
        lease_seconds=60,
        now=start + timedelta(seconds=12),
    )
    renewed = await renew_lease(
        runtime_session,
        current_lease,
        lease_seconds=60,
        now=start + timedelta(seconds=12),
    )
    assert renewed is not None
    assert renewed.expires_at == start + timedelta(seconds=72)


@pytest.mark.asyncio
async def test_terminal_failure_is_guarded_by_fencing_token(
    runtime_session: AsyncSession,
):
    fail_run = getattr(task_runtime, "fail_run", None)
    assert callable(fail_run), "runtime must expose fail_run"

    run = await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="rag_index",
        scope_type="revision",
        scope_id=313,
        trigger_type="on_ingest",
        queue_name="default",
    )
    await runtime_session.flush()
    start = datetime.now(timezone.utc)
    old_lease = await claim_run(
        runtime_session,
        run.id,
        worker_id="worker-a",
        lease_seconds=10,
        now=start,
    )
    assert old_lease is not None
    current_lease = await claim_run(
        runtime_session,
        run.id,
        worker_id="worker-b",
        lease_seconds=60,
        now=start + timedelta(seconds=11),
    )
    assert current_lease is not None

    assert not await fail_run(
        runtime_session,
        old_lease,
        error_code="stale_worker",
        error_message="must be rejected",
        now=start + timedelta(seconds=12),
    )
    assert await fail_run(
        runtime_session,
        current_lease,
        error_code="embedding_invalid",
        error_message="invalid vector",
        now=start + timedelta(seconds=12),
    )
    await runtime_session.flush()
    assert run.status == "failed"
    assert run.error_code == "embedding_invalid"
    assert run.error_message == "invalid vector"


@pytest.mark.asyncio
async def test_each_worker_execution_creates_a_new_attempt_span(
    runtime_session: AsyncSession,
):
    start_attempt = getattr(task_runtime, "start_worker_attempt", None)
    finish_attempt = getattr(task_runtime, "finish_worker_attempt", None)
    assert callable(start_attempt), "runtime must expose start_worker_attempt"
    assert callable(finish_attempt), "runtime must expose finish_worker_attempt"

    run = await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=314,
        trigger_type="manual",
        queue_name="default",
    )
    await runtime_session.flush()
    now = datetime.now(timezone.utc)
    lease = await claim_run(
        runtime_session,
        run.id,
        worker_id="worker-a",
        lease_seconds=60,
        now=now,
    )
    assert lease is not None

    first = await start_attempt(runtime_session, run, lease, now=now)
    assert first.metrics == {"attempt": 1, "execution_epoch": 1}
    assert await finish_attempt(
        runtime_session,
        first.id,
        status="failed",
        error_code="temporary_failure",
        error_message="retrying",
        now=now + timedelta(seconds=1),
    )
    assert await retry_run(
        runtime_session,
        lease,
        queue_name="default",
        available_at=now + timedelta(seconds=2),
        error_code="temporary_failure",
        now=now + timedelta(seconds=1),
    )
    second_lease = await claim_run(
        runtime_session,
        run.id,
        worker_id="worker-b",
        lease_seconds=60,
        now=now + timedelta(seconds=2),
    )
    assert second_lease is not None
    second = await start_attempt(
        runtime_session,
        run,
        second_lease,
        now=now + timedelta(seconds=2),
    )
    assert second.metrics == {"attempt": 2, "execution_epoch": 2}

    spans = (
        await runtime_session.execute(
            select(ProcessingSpan)
            .where(
                ProcessingSpan.run_id == run.id,
                ProcessingSpan.span_name == "worker_attempt",
            )
            .order_by(ProcessingSpan.id)
        )
    ).scalars().all()
    assert [span.status for span in spans] == ["failed", "running"]


@pytest.mark.asyncio
async def test_reaper_republishes_expired_running_run_once(
    runtime_session: AsyncSession,
):
    task_reaper = _reaper_module()
    recover = getattr(task_reaper, "recover_stalled_runs", None)
    assert callable(recover), "reaper must expose recover_stalled_runs"

    run = await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="document_process",
        scope_type="revision",
        scope_id=315,
        trigger_type="manual",
        queue_name="default",
    )
    await runtime_session.flush()
    now = datetime.now(timezone.utc)
    lease = await claim_run(
        runtime_session,
        run.id,
        worker_id="worker-a",
        lease_seconds=10,
        now=now,
    )
    assert lease is not None
    original = (
        await runtime_session.execute(
            select(TaskOutbox).where(TaskOutbox.run_id == run.id)
        )
    ).scalar_one()
    original.published_at = now
    await runtime_session.flush()

    recovered = await recover(
        runtime_session,
        batch_size=10,
        stale_after_seconds=30,
        now=now + timedelta(seconds=31),
    )
    assert recovered == [run.id]
    assert await recover(
        runtime_session,
        batch_size=10,
        stale_after_seconds=30,
        now=now + timedelta(seconds=31),
    ) == []
    outboxes = (
        await runtime_session.execute(
            select(TaskOutbox)
            .where(TaskOutbox.run_id == run.id)
            .order_by(TaskOutbox.id)
        )
    ).scalars().all()
    assert len(outboxes) == 2
    assert outboxes[-1].queue_name == "llmwiki:tasks:default"


@pytest.mark.asyncio
async def test_reaper_does_not_duplicate_existing_unpublished_outbox(
    runtime_session: AsyncSession,
):
    task_reaper = _reaper_module()
    recover = getattr(task_reaper, "recover_stalled_runs", None)
    assert callable(recover), "reaper must expose recover_stalled_runs"

    run = await create_run_with_outbox(
        runtime_session,
        tenant_id=101,
        kb_id=202,
        run_type="rag_index",
        scope_type="revision",
        scope_id=316,
        trigger_type="on_ingest",
        queue_name="critical",
    )
    await runtime_session.flush()
    old = datetime.now(timezone.utc) - timedelta(minutes=10)
    run.created_at = old
    await runtime_session.flush()

    assert await recover(
        runtime_session,
        batch_size=10,
        stale_after_seconds=30,
        now=datetime.now(timezone.utc),
    ) == []
