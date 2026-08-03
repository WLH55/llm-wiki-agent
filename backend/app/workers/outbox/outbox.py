"""Transactional Outbox 的并发领取与发布结果持久化。"""

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_runtime import TaskOutbox


@dataclass(frozen=True)
class OutboxClaim:
    """Publisher 对一条 Outbox 的短期领取凭证。"""

    outbox_id: int
    run_id: int
    task_name: str
    queue_name: str
    publish_attempts: int
    lock_token: UUID
    locked_until: datetime

    def with_lock_token(self, token: UUID | str) -> "OutboxClaim":
        """构造不同 token 的 claim，主要用于验证 fencing。"""
        return replace(self, lock_token=UUID(str(token)))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def claim_outbox_batch(
    db: AsyncSession,
    *,
    batch_size: int,
    lock_seconds: int,
    now: datetime | None = None,
) -> list[OutboxClaim]:
    """使用 SKIP LOCKED 领取一批可投递消息。"""
    claim_time = now or _utc_now()
    locked_until = claim_time + timedelta(seconds=lock_seconds)
    result = await db.execute(
        select(TaskOutbox)
        .where(
            TaskOutbox.published_at.is_(None),
            TaskOutbox.available_at <= claim_time,
            or_(
                TaskOutbox.lock_token.is_(None),
                TaskOutbox.locked_until < claim_time,
            ),
        )
        .order_by(TaskOutbox.available_at, TaskOutbox.id)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    claims: list[OutboxClaim] = []
    for outbox in result.scalars():
        token = uuid4()
        outbox.lock_token = token
        outbox.locked_until = locked_until
        outbox.updated_at = claim_time
        claims.append(
            OutboxClaim(
                outbox_id=outbox.id,
                run_id=outbox.run_id,
                task_name=outbox.task_name,
                queue_name=outbox.queue_name,
                publish_attempts=outbox.publish_attempts,
                lock_token=token,
                locked_until=locked_until,
            )
        )
    await db.flush()
    return claims


async def mark_outbox_published(
    db: AsyncSession,
    claim: OutboxClaim,
    *,
    now: datetime | None = None,
) -> bool:
    """只有当前未过期 claim 才能确认发布成功。"""
    published_at = now or _utc_now()
    statement = (
        update(TaskOutbox)
        .where(
            TaskOutbox.id == claim.outbox_id,
            TaskOutbox.published_at.is_(None),
            TaskOutbox.lock_token == claim.lock_token,
            TaskOutbox.locked_until > published_at,
        )
        .values(
            published_at=published_at,
            publish_attempts=TaskOutbox.publish_attempts + 1,
            lock_token=None,
            locked_until=None,
            last_error=None,
            updated_at=published_at,
        )
        .execution_options(synchronize_session="fetch")
        .returning(TaskOutbox.id)
    )
    return (await db.execute(statement)).scalar_one_or_none() is not None


async def release_outbox_claim(
    db: AsyncSession,
    claim: OutboxClaim,
    *,
    error: str,
    retry_at: datetime,
    now: datetime | None = None,
) -> bool:
    """记录发布错误并释放 claim，保留 Outbox 供稍后重试。"""
    released_at = now or _utc_now()
    statement = (
        update(TaskOutbox)
        .where(
            TaskOutbox.id == claim.outbox_id,
            TaskOutbox.published_at.is_(None),
            TaskOutbox.lock_token == claim.lock_token,
        )
        .values(
            available_at=retry_at,
            publish_attempts=TaskOutbox.publish_attempts + 1,
            lock_token=None,
            locked_until=None,
            last_error=error[:2000],
            updated_at=released_at,
        )
        .execution_options(synchronize_session="fetch")
        .returning(TaskOutbox.id)
    )
    return (await db.execute(statement)).scalar_one_or_none() is not None
