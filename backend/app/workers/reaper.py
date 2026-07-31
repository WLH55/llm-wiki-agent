"""补偿长期未执行或租约过期的 Run，避免已发布消息永久失联。"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_runtime import ProcessingRun, TaskOutbox
from app.workers.executor import queue_name_for_run


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def recover_stalled_runs(
    db: AsyncSession,
    *,
    batch_size: int,
    stale_after_seconds: float,
    now: datetime | None = None,
) -> list[int]:
    """为卡住且没有待发消息的 Run 补 Outbox；重复执行是安全的。"""
    recovery_time = now or _utc_now()
    stale_before = recovery_time - timedelta(seconds=stale_after_seconds)
    unpublished_exists = exists(
        select(TaskOutbox.id).where(
            TaskOutbox.run_id == ProcessingRun.id,
            TaskOutbox.published_at.is_(None),
        )
    )
    result = await db.execute(
        select(ProcessingRun)
        .where(
            or_(
                and_(
                    ProcessingRun.status == "pending",
                    ProcessingRun.created_at <= stale_before,
                ),
                and_(
                    ProcessingRun.status == "running",
                    ProcessingRun.lease_expires_at <= recovery_time,
                ),
            ),
            ~unpublished_exists,
        )
        .order_by(ProcessingRun.created_at, ProcessingRun.id)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    recovered: list[int] = []
    for run in result.scalars():
        db.add(
            TaskOutbox(
                run_id=run.id,
                task_name="process_run",
                queue_name=queue_name_for_run(run.run_type),
                available_at=recovery_time,
                last_error="reaper_recovery",
            )
        )
        recovered.append(run.id)
    await db.flush()
    return recovered
