"""Processing Run 的原子领取、fencing 与自动重试事务。"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_runtime import ProcessingRun, ProcessingSpan, TaskOutbox


@dataclass(frozen=True)
class ExecutionLease:
    """Worker 当前持有的有期限执行凭证。"""

    run_id: int
    token: UUID
    epoch: int
    worker_id: str
    expires_at: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def create_run_with_outbox(
    db: AsyncSession,
    *,
    tenant_id: int,
    kb_id: int,
    run_type: str,
    scope_type: str,
    scope_id: int,
    trigger_type: str,
    queue_name: str,
    parent_run_id: int | None = None,
    retry_of_run_id: int | None = None,
    attempt_no: int = 1,
    idempotency_key: str | None = None,
    effective_config_version: int | None = None,
    options_snapshot: dict | None = None,
    requested_by_user_id: int | None = None,
    available_at: datetime | None = None,
) -> ProcessingRun:
    """在调用方事务中同时创建 Run 与待投递 Outbox。"""
    run = ProcessingRun(
        tenant_id=tenant_id,
        kb_id=kb_id,
        run_type=run_type,
        scope_type=scope_type,
        scope_id=scope_id,
        parent_run_id=parent_run_id,
        retry_of_run_id=retry_of_run_id,
        attempt_no=attempt_no,
        trigger_type=trigger_type,
        idempotency_key=idempotency_key,
        effective_config_version=effective_config_version,
        options_snapshot=options_snapshot or {},
        requested_by_user_id=requested_by_user_id,
    )
    db.add(run)
    await db.flush()
    db.add(
        TaskOutbox(
            run_id=run.id,
            task_name="process_run",
            queue_name=queue_name,
            available_at=available_at or _utc_now(),
        )
    )
    return run


async def claim_run(
    db: AsyncSession,
    run_id: int,
    *,
    worker_id: str,
    lease_seconds: int,
    now: datetime | None = None,
) -> ExecutionLease | None:
    """原子领取 pending Run，或接管租约已过期的 running Run。"""
    claim_time = now or _utc_now()
    token = uuid4()
    expires_at = claim_time + timedelta(seconds=lease_seconds)
    statement = (
        update(ProcessingRun)
        .where(
            ProcessingRun.id == run_id,
            or_(
                ProcessingRun.status == "pending",
                and_(
                    ProcessingRun.status == "running",
                    ProcessingRun.lease_expires_at < claim_time,
                ),
            ),
        )
        .values(
            status="running",
            execution_token=token,
            execution_epoch=ProcessingRun.execution_epoch + 1,
            lease_expires_at=expires_at,
            worker_id=worker_id,
            started_at=func.coalesce(ProcessingRun.started_at, claim_time),
            heartbeat_at=claim_time,
            finished_at=None,
            updated_at=claim_time,
        )
        .execution_options(synchronize_session="fetch")
        .returning(ProcessingRun.execution_epoch)
    )
    epoch = (await db.execute(statement)).scalar_one_or_none()
    if epoch is None:
        return None
    return ExecutionLease(
        run_id=run_id,
        token=token,
        epoch=epoch,
        worker_id=worker_id,
        expires_at=expires_at,
    )


def _current_lease_predicate(
    lease: ExecutionLease,
    now: datetime,
) -> tuple:
    return (
        ProcessingRun.id == lease.run_id,
        ProcessingRun.status == "running",
        ProcessingRun.execution_token == lease.token,
        ProcessingRun.execution_epoch == lease.epoch,
        ProcessingRun.lease_expires_at > now,
    )


async def complete_run(
    db: AsyncSession,
    lease: ExecutionLease,
    *,
    now: datetime | None = None,
) -> bool:
    """仅允许当前未过期租约将 Run 提交为成功。"""
    finished_at = now or _utc_now()
    statement = (
        update(ProcessingRun)
        .where(*_current_lease_predicate(lease, finished_at))
        .values(
            status="succeeded",
            execution_token=None,
            lease_expires_at=None,
            worker_id=None,
            heartbeat_at=finished_at,
            finished_at=finished_at,
            updated_at=finished_at,
        )
        .execution_options(synchronize_session="fetch", populate_existing=True)
        .returning(ProcessingRun)
    )
    return (await db.execute(statement)).scalar_one_or_none() is not None


async def renew_lease(
    db: AsyncSession,
    lease: ExecutionLease,
    *,
    lease_seconds: int,
    now: datetime | None = None,
) -> ExecutionLease | None:
    """续租当前执行权；过期或已被接管的 Worker 无权恢复租约。"""
    heartbeat_at = now or _utc_now()
    expires_at = heartbeat_at + timedelta(seconds=lease_seconds)
    statement = (
        update(ProcessingRun)
        .where(*_current_lease_predicate(lease, heartbeat_at))
        .values(
            lease_expires_at=expires_at,
            heartbeat_at=heartbeat_at,
            updated_at=heartbeat_at,
        )
        .execution_options(synchronize_session="fetch")
        .returning(ProcessingRun.id)
    )
    if (await db.execute(statement)).scalar_one_or_none() is None:
        return None
    return ExecutionLease(
        run_id=lease.run_id,
        token=lease.token,
        epoch=lease.epoch,
        worker_id=lease.worker_id,
        expires_at=expires_at,
    )


async def fail_run(
    db: AsyncSession,
    lease: ExecutionLease,
    *,
    error_code: str,
    error_message: str,
    now: datetime | None = None,
) -> bool:
    """仅允许当前租约把 Run 置为不可自动重试的失败终态。"""
    finished_at = now or _utc_now()
    statement = (
        update(ProcessingRun)
        .where(*_current_lease_predicate(lease, finished_at))
        .values(
            status="failed",
            execution_token=None,
            lease_expires_at=None,
            worker_id=None,
            heartbeat_at=finished_at,
            error_code=error_code[:50],
            error_message=error_message[:1000],
            finished_at=finished_at,
            updated_at=finished_at,
        )
        .execution_options(synchronize_session="fetch", populate_existing=True)
        .returning(ProcessingRun)
    )
    return (await db.execute(statement)).scalar_one_or_none() is not None


async def start_worker_attempt(
    db: AsyncSession,
    run: ProcessingRun,
    lease: ExecutionLease,
    *,
    now: datetime | None = None,
) -> ProcessingSpan:
    """为每次消息执行新增 Span，自动重试不会覆盖上一轮诊断记录。"""
    started_at = now or _utc_now()
    attempt = (
        await db.execute(
            select(func.count(ProcessingSpan.id)).where(
                ProcessingSpan.run_id == run.id,
                ProcessingSpan.span_name == "worker_attempt",
            )
        )
    ).scalar_one() + 1
    span = ProcessingSpan(
        tenant_id=run.tenant_id,
        kb_id=run.kb_id,
        run_id=run.id,
        span_name="worker_attempt",
        status="running",
        metrics={"attempt": attempt, "execution_epoch": lease.epoch},
        started_at=started_at,
    )
    db.add(span)
    await db.flush()
    return span


async def finish_worker_attempt(
    db: AsyncSession,
    span_id: int,
    *,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
    now: datetime | None = None,
) -> bool:
    """结束一轮 Worker 执行记录，不允许重复覆盖已结束的 Span。"""
    if status not in {"succeeded", "failed", "cancelled"}:
        raise ValueError(f"invalid worker attempt status: {status}")
    finished_at = now or _utc_now()
    statement = (
        update(ProcessingSpan)
        .where(
            ProcessingSpan.id == span_id,
            ProcessingSpan.span_name == "worker_attempt",
            ProcessingSpan.status == "running",
        )
        .values(
            status=status,
            error_code=error_code[:50] if error_code else None,
            error_message=error_message[:1000] if error_message else None,
            finished_at=finished_at,
            updated_at=finished_at,
        )
        .execution_options(synchronize_session="fetch")
        .returning(ProcessingSpan.id)
    )
    return (await db.execute(statement)).scalar_one_or_none() is not None


async def retry_run(
    db: AsyncSession,
    lease: ExecutionLease,
    *,
    queue_name: str,
    available_at: datetime,
    error_code: str,
    now: datetime | None = None,
) -> bool:
    """释放当前租约，并在同一事务内为相同 Run 创建延迟重投。"""
    retry_at = now or _utc_now()
    statement = (
        update(ProcessingRun)
        .where(*_current_lease_predicate(lease, retry_at))
        .values(
            status="pending",
            execution_token=None,
            lease_expires_at=None,
            worker_id=None,
            heartbeat_at=None,
            error_code=None,
            error_message=None,
            finished_at=None,
            updated_at=retry_at,
        )
        .execution_options(synchronize_session="fetch")
        .returning(ProcessingRun.id)
    )
    updated_id = (await db.execute(statement)).scalar_one_or_none()
    if updated_id is None:
        return False
    db.add(
        TaskOutbox(
            run_id=lease.run_id,
            task_name="process_run",
            queue_name=queue_name,
            available_at=available_at,
            last_error=error_code[:1000],
        )
    )
    return True
