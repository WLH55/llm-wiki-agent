"""Outbox 到消息 Broker 的发布编排。"""

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.workers.outbox.outbox import (
    OutboxClaim,
    mark_outbox_published,
    release_outbox_claim,
)

TaskSender = Callable[[str, int, str], Awaitable[None]]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def publish_outbox_claim(
    db: AsyncSession,
    claim: OutboxClaim,
    *,
    sender: TaskSender,
    now: datetime | None = None,
    retry_delay_seconds: int = 5,
) -> bool:
    """发布一条只含 Run 身份的消息，并持久化发布结果。"""
    publish_time = now or _utc_now()
    try:
        await sender(claim.task_name, claim.run_id, claim.queue_name)
    except Exception as exc:
        await release_outbox_claim(
            db,
            claim,
            error=str(exc),
            retry_at=publish_time + timedelta(seconds=retry_delay_seconds),
            now=publish_time,
        )
        return False
    return await mark_outbox_published(db, claim, now=publish_time)
