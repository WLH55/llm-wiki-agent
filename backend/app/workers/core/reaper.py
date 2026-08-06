"""Reaper：嵌入 worker 进程的卡死 Run 恢复扫描（对齐 WeKnora housekeeping）。

两类卡死 Run：
1. running 且 MAX(spans.updated_at) 超 span_stale_seconds 没动（span 心跳超时）
2. pending 且 updated_at 超 pending_stale_seconds 没动（入队失败/丢失）

动作：标 Run failed，不自动重投（用户手动重试）。

运行方式：独立线程循环，由 ReaperMiddleware 在 after_process_boot 启动，
before_worker_shutdown 停止。
"""

import asyncio
import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.task_runtime import ProcessingRun, ProcessingSpan
from app.workers.core.constants import ErrorCode, RunStatus, SpanStatus

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def recover_stalled_runs(
    db: AsyncSession,
    *,
    span_stale_seconds: float,
    pending_stale_seconds: float,
    batch_size: int = 100,
) -> list[int]:
    """扫描卡死 Run 并标 failed：
    1. running 且 MAX(spans.updated_at) 超 span_stale_seconds 没动
    2. pending 且 updated_at 超 pending_stale_seconds 没动（release_run 会刷新，重试等待期不误杀）
    返回标 failed 的 run_id 列表。
    """
    cutoff = _utc_now()
    span_cutoff = cutoff - timedelta(seconds=span_stale_seconds)
    pending_cutoff = cutoff - timedelta(seconds=pending_stale_seconds)

    # 子查询：每个 run 的 MAX(spans.updated_at)（只看 running span）
            # 已结束的 span 不影响心跳判断
    span_heartbeat = (
        select(
            ProcessingSpan.run_id,
            func.max(ProcessingSpan.updated_at).label("last_span_at"),
        )
        .where(ProcessingSpan.status == SpanStatus.RUNNING)
        .group_by(ProcessingSpan.run_id)
        .subquery()
    )

    # 扫描卡死 Run：
    # 1. running 且 started_at < span_cutoff（避免误杀刚启动的 Run）
    #    且 (无 running span 或 MAX(spans.updated_at) < span_cutoff)
    # 2. pending 且 updated_at < pending_cutoff（入队失败/丢失）
    stalled = (
        select(ProcessingRun.id)
        .outerjoin(span_heartbeat, span_heartbeat.c.run_id == ProcessingRun.id)
        .where(
            or_(
                and_(
                    ProcessingRun.status == RunStatus.RUNNING,
                    ProcessingRun.started_at < span_cutoff,
                    or_(
                        span_heartbeat.c.last_span_at.is_(None),
                        span_heartbeat.c.last_span_at < span_cutoff,
                    ),
                ),
                and_(
                    ProcessingRun.status == RunStatus.PENDING,
                    ProcessingRun.updated_at < pending_cutoff,
                ),
            ),
        )
        .limit(batch_size)
    )
    stalled_ids = list((await db.execute(stalled)).scalars())

    if not stalled_ids:
        return []

    # 批量标 failed（CAS status IN running/pending 防止误杀已终态的 Run）
    statement = (
        update(ProcessingRun)
        .where(
            ProcessingRun.id.in_(stalled_ids),
            ProcessingRun.status.in_([RunStatus.RUNNING, RunStatus.PENDING]),
        )
        .values(
            status=RunStatus.FAILED,
            error_code=ErrorCode.REAPER_RECOVERED,
            error_message="run stalled, recovered by reaper",
            finished_at=cutoff,
            updated_at=cutoff,
        )
        .returning(ProcessingRun.id)
    )
    recovered = list((await db.execute(statement)).scalars())

    if recovered:
        logger.info("reaper recovered %d stalled runs: %s", len(recovered), recovered)
    return recovered


async def _recover_once(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    span_stale_seconds: float,
    pending_stale_seconds: float,
    batch_size: int,
) -> list[int]:
    """开 session + 事务，调 recover_stalled_runs（供独立线程循环使用）。"""
    async with session_factory() as db:
        async with db.begin():
            return await recover_stalled_runs(
                db,
                span_stale_seconds=span_stale_seconds,
                pending_stale_seconds=pending_stale_seconds,
                batch_size=batch_size,
            )


def run_reaper_loop(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    interval_seconds: float,
    span_stale_seconds: float,
    pending_stale_seconds: float,
    stop: threading.Event,
    batch_size: int = 100,
) -> None:
    """独立线程循环：每 interval_seconds 调一次 recover_stalled_runs。

    在 worker 子进程的独立线程中运行，由 ReaperMiddleware 控制：
    - after_process_boot：启动本循环
    - before_worker_shutdown：set stop event 停止循环
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        logger.info(
            "reaper loop started: interval=%ss span_stale=%ss pending_stale=%ss",
            interval_seconds, span_stale_seconds, pending_stale_seconds,
        )
        while not stop.is_set():
            try:
                loop.run_until_complete(
                    _recover_once(
                        session_factory,
                        span_stale_seconds=span_stale_seconds,
                        pending_stale_seconds=pending_stale_seconds,
                        batch_size=batch_size,
                    )
                )
            except Exception:
                logger.exception("reaper loop iteration failed")
            # 可中断的等待：stop.set() 立即唤醒
            stop.wait(timeout=interval_seconds)
        logger.info("reaper loop stopped")
    finally:
        loop.close()
