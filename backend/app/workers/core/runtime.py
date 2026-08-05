"""Processing Run 的原子领取与状态转换（Dramatiq 模式，无 fencing）。"""

from datetime import datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_runtime import ProcessingRun, ProcessingSpan
from app.workers.core.constants import (
    ErrorCode,
    RunStatus,
    SpanName,
    SpanStatus,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def create_run(
    db: AsyncSession,
    *,
    tenant_id: int,
    kb_id: int,
    run_type: str,
    scope_type: str,
    scope_id: int,
    trigger_type: str,
    parent_run_id: int | None = None,
    retry_of_run_id: int | None = None,
    attempt_no: int = 1,
    idempotency_key: str | None = None,
    effective_config_version: int | None = None,
    options_snapshot: dict | None = None,
    requested_by_user_id: int | None = None,
) -> ProcessingRun:
    """在调用方事务中创建 Run 行（不写 Outbox）。

    Dramatiq 模式下调用方在事务提交后调 enqueue_run 入队，DB 与入队不再强一致。
    """
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
    return run


async def claim_run(
    db: AsyncSession,
    run_id: int,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> bool:
    """原子 CAS：pending -> running。返回是否领取成功。

    fencing 移除后 worker_id 不再持久化到 Run 行，参数保留以维持调用方契约。
    重复投递被吸收：若 Run 已是 running 或终态，返回 False。
    """
    claim_time = now or _utc_now()
    statement = (
        update(ProcessingRun)
        .where(
            ProcessingRun.id == run_id,
            ProcessingRun.status == RunStatus.PENDING,
        )
        .values(
            status=RunStatus.RUNNING,
            started_at=func.coalesce(ProcessingRun.started_at, claim_time),
            updated_at=claim_time,
        )
        .execution_options(synchronize_session="fetch")
        .returning(ProcessingRun.id)
    )
    return (await db.execute(statement)).scalar_one_or_none() is not None


async def complete_run(
    db: AsyncSession,
    run_id: int,
    *,
    now: datetime | None = None,
) -> bool:
    """原子 CAS：running -> succeeded。返回是否成功。"""
    finished_at = now or _utc_now()
    statement = (
        update(ProcessingRun)
        .where(
            ProcessingRun.id == run_id,
            ProcessingRun.status == RunStatus.RUNNING,
        )
        .values(
            status=RunStatus.SUCCEEDED,
            finished_at=finished_at,
            updated_at=finished_at,
        )
        .execution_options(synchronize_session="fetch")
        .returning(ProcessingRun.id)
    )
    return (await db.execute(statement)).scalar_one_or_none() is not None


async def fail_run(
    db: AsyncSession,
    run_id: int,
    *,
    error_code: str,
    error_message: str,
    now: datetime | None = None,
) -> bool:
    """原子 CAS：running -> failed。返回是否成功。"""
    finished_at = now or _utc_now()
    statement = (
        update(ProcessingRun)
        .where(
            ProcessingRun.id == run_id,
            ProcessingRun.status == RunStatus.RUNNING,
        )
        .values(
            status=RunStatus.FAILED,
            error_code=error_code[:50],
            error_message=error_message[:1000],
            finished_at=finished_at,
            updated_at=finished_at,
        )
        .execution_options(synchronize_session="fetch")
        .returning(ProcessingRun.id)
    )
    return (await db.execute(statement)).scalar_one_or_none() is not None


async def mark_run_enqueue_failed(
    db: AsyncSession,
    run_id: int,
    *,
    error_message: str,
    now: datetime | None = None,
) -> None:
    """入队失败时标 Run failed，用户可见可重试。

    场景：DB 提交成功但 Dramatiq enqueue 抛异常（如 Redis 故障）。
    此时 Run 已是 pending，需要标 failed 让用户可见。
    """
    marked_at = now or _utc_now()
    statement = (
        update(ProcessingRun)
        .where(
            ProcessingRun.id == run_id,
            ProcessingRun.status == RunStatus.PENDING,
        )
        .values(
            status=RunStatus.FAILED,
            error_code=ErrorCode.ENQUEUE_FAILED,
            error_message=error_message[:1000],
            finished_at=marked_at,
            updated_at=marked_at,
        )
        .execution_options(synchronize_session="fetch")
    )
    await db.execute(statement)


async def start_worker_attempt(
    db: AsyncSession,
    run: ProcessingRun,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> ProcessingSpan:
    """为每次消息执行新增 Span，自动重试不会覆盖上一轮诊断记录。"""
    started_at = now or _utc_now()
    attempt = (
        await db.execute(
            select(func.count(ProcessingSpan.id)).where(
                ProcessingSpan.run_id == run.id,
                ProcessingSpan.span_name == SpanName.WORKER_ATTEMPT,
            )
        )
    ).scalar_one() + 1
    span = ProcessingSpan(
        tenant_id=run.tenant_id,
        kb_id=run.kb_id,
        run_id=run.id,
        span_name=SpanName.WORKER_ATTEMPT,
        status=SpanStatus.RUNNING,
        metrics={"attempt": attempt, "worker_id": worker_id},
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
    if status not in {SpanStatus.SUCCEEDED, SpanStatus.FAILED, SpanStatus.CANCELLED}:
        raise ValueError(f"invalid worker attempt status: {status}")
    finished_at = now or _utc_now()
    statement = (
        update(ProcessingSpan)
        .where(
            ProcessingSpan.id == span_id,
            ProcessingSpan.span_name == SpanName.WORKER_ATTEMPT,
            ProcessingSpan.status == SpanStatus.RUNNING,
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
