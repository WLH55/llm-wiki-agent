"""Outbox Publisher 后台批处理事务边界测试。"""

import importlib
import importlib.util
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.models.database import async_engine, async_session_factory
from app.models.task_runtime import ProcessingRun, ProcessingSpan, TaskOutbox
from app.workers.core.runtime import create_run_with_outbox

TEST_TENANT_ID = 98_002


def _service_module():
    spec = importlib.util.find_spec("app.workers.outbox.outbox_service")
    assert spec is not None, "app.workers.outbox.outbox_service must exist"
    return importlib.import_module("app.workers.outbox.outbox_service")


@pytest_asyncio.fixture(autouse=True)
async def clean_service_rows() -> AsyncIterator[None]:
    await async_engine.dispose()
    for _ in range(2):
        async with async_session_factory() as db:
            run_ids = select(ProcessingRun.id).where(
                ProcessingRun.tenant_id == TEST_TENANT_ID
            )
            await db.execute(delete(TaskOutbox).where(TaskOutbox.run_id.in_(run_ids)))
            await db.execute(
                delete(ProcessingSpan).where(ProcessingSpan.run_id.in_(run_ids))
            )
            await db.execute(
                delete(ProcessingRun).where(ProcessingRun.tenant_id == TEST_TENANT_ID)
            )
            await db.commit()
        if _ == 0:
            yield
    await async_engine.dispose()


async def _create_runs(count: int) -> list[int]:
    async with async_session_factory() as db:
        async with db.begin():
            runs = [
                await create_run_with_outbox(
                    db,
                    tenant_id=TEST_TENANT_ID,
                    kb_id=202,
                    run_type="document_process",
                    scope_type="revision",
                    scope_id=400 + index,
                    trigger_type="manual",
                    queue_name="llmwiki:tasks:default",
                )
                for index in range(count)
            ]
        return [run.id for run in runs]


@pytest.mark.asyncio
async def test_batch_publishes_each_claim_and_confirms_independently():
    service = _service_module()
    run_ids = await _create_runs(2)
    sent: list[tuple[str, int, str]] = []

    async def sender(task_name: str, run_id: int, queue_name: str) -> None:
        sent.append((task_name, run_id, queue_name))

    result = await service.publish_outbox_batch(
        session_factory=async_session_factory,
        sender=sender,
        batch_size=10,
        lock_seconds=30,
        retry_base_seconds=1,
        retry_max_seconds=60,
        retry_jitter=lambda delay: 0,
    )
    assert result.claimed == 2
    assert result.published == 2
    assert result.failed == 0
    assert [item[1] for item in sent] == run_ids
    async with async_session_factory() as db:
        outboxes = (
            await db.execute(
                select(TaskOutbox)
                .where(TaskOutbox.run_id.in_(run_ids))
                .order_by(TaskOutbox.id)
            )
        ).scalars().all()
    assert all(item.published_at is not None for item in outboxes)


@pytest.mark.asyncio
async def test_batch_keeps_failed_publication_for_later_retry():
    service = _service_module()
    run_id = (await _create_runs(1))[0]

    async def failing_sender(task_name: str, run_id: int, queue_name: str) -> None:
        raise ConnectionError("redis unavailable")

    result = await service.publish_outbox_batch(
        session_factory=async_session_factory,
        sender=failing_sender,
        batch_size=10,
        lock_seconds=30,
        retry_base_seconds=5,
        retry_max_seconds=60,
        retry_jitter=lambda delay: 0,
    )
    assert result.claimed == 1
    assert result.published == 0
    assert result.failed == 1
    async with async_session_factory() as db:
        outbox = (
            await db.execute(select(TaskOutbox).where(TaskOutbox.run_id == run_id))
        ).scalar_one()
    assert outbox.published_at is None
    assert outbox.publish_attempts == 1
    assert outbox.lock_token is None
    assert outbox.last_error == "redis unavailable"
