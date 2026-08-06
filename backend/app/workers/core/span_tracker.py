"""Span 心跳 API（by-name shim + ctx pattern）：对齐 WeKnora SpanTracker 4 事件。

best-effort：所有 DB 操作的错误都 log + swallow，不阻断业务流水线。
processing_runs.status 是真相源，spans 只是观测层。

唯一键：(run_id, attempt_no, span_name)。每次重试 attempt_no + 1 是新 span 行，
事件流水清晰，便于事后排查"哪一次重试在哪一步挂了"。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import update

from app.models.task_runtime import ProcessingSpan
from app.workers.core.constants import SpanStatus

if TYPE_CHECKING:
    from app.workers.core.executor import RunExecutionContext

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _span_predicate(ctx: RunExecutionContext, span_name: str) -> tuple:
    """按 (run_id, attempt_no, span_name) 定位 span 行。"""
    return (
        ProcessingSpan.run_id == ctx.identity.run_id,
        ProcessingSpan.attempt_no == ctx.identity.execution_attempt,
        ProcessingSpan.span_name == span_name,
    )


async def begin_span(
    ctx: RunExecutionContext,
    span_name: str,
    *,
    input_summary: dict | None = None,
) -> None:
    """开始阶段 span：(run_id, attempt_no, span_name) 唯一。

    best-effort：DB 错误 log + swallow，不阻断流水线。刷 spans.updated_at 作为心跳。
    """
    started_at = _utc_now()
    span = ProcessingSpan(
        tenant_id=ctx.identity.tenant_id,
        kb_id=ctx.identity.kb_id,
        run_id=ctx.identity.run_id,
        span_name=span_name,
        attempt_no=ctx.identity.execution_attempt,
        status=SpanStatus.RUNNING,
        metrics=input_summary or {},
        started_at=started_at,
    )
    try:
        async with ctx.session_factory() as db:
            async with db.begin():
                db.add(span)
                await db.flush()
    except Exception:
        logger.exception(
            "span_tracker.begin_span failed: run_id=%s attempt=%s name=%s",
            ctx.identity.run_id,
            ctx.identity.execution_attempt,
            span_name,
        )


async def end_span(
    ctx: RunExecutionContext,
    span_name: str,
    *,
    output_summary: dict | None = None,
) -> None:
    """结束 span：status=succeeded + finished_at + output_summary。best-effort。"""
    finished_at = _utc_now()
    try:
        async with ctx.session_factory() as db:
            async with db.begin():
                statement = (
                    update(ProcessingSpan)
                    .where(
                        *_span_predicate(ctx, span_name),
                        ProcessingSpan.status == SpanStatus.RUNNING,
                    )
                    .values(
                        status=SpanStatus.SUCCEEDED,
                        metrics=output_summary or {},
                        finished_at=finished_at,
                        updated_at=finished_at,
                    )
                )
                await db.execute(statement)
    except Exception:
        logger.exception(
            "span_tracker.end_span failed: run_id=%s attempt=%s name=%s",
            ctx.identity.run_id,
            ctx.identity.execution_attempt,
            span_name,
        )


async def fail_span(
    ctx: RunExecutionContext,
    span_name: str,
    *,
    error_code: str,
    error_message: str,
) -> None:
    """失败 span：status=failed + finished_at + error_code/message。best-effort。"""
    finished_at = _utc_now()
    try:
        async with ctx.session_factory() as db:
            async with db.begin():
                statement = (
                    update(ProcessingSpan)
                    .where(
                        *_span_predicate(ctx, span_name),
                        ProcessingSpan.status == SpanStatus.RUNNING,
                    )
                    .values(
                        status=SpanStatus.FAILED,
                        error_code=error_code[:50],
                        error_message=error_message[:1000],
                        finished_at=finished_at,
                        updated_at=finished_at,
                    )
                )
                await db.execute(statement)
    except Exception:
        logger.exception(
            "span_tracker.fail_span failed: run_id=%s attempt=%s name=%s",
            ctx.identity.run_id,
            ctx.identity.execution_attempt,
            span_name,
        )


async def skip_span(
    ctx: RunExecutionContext,
    span_name: str,
    *,
    reason: str,
) -> None:
    """跳过 span（幂等检查命中跳过阶段）：status=skipped + finished_at。best-effort。"""
    finished_at = _utc_now()
    try:
        async with ctx.session_factory() as db:
            async with db.begin():
                statement = (
                    update(ProcessingSpan)
                    .where(
                        *_span_predicate(ctx, span_name),
                        ProcessingSpan.status == SpanStatus.RUNNING,
                    )
                    .values(
                        status=SpanStatus.SKIPPED,
                        metrics={"reason": reason},
                        finished_at=finished_at,
                        updated_at=finished_at,
                    )
                )
                await db.execute(statement)
    except Exception:
        logger.exception(
            "span_tracker.skip_span failed: run_id=%s attempt=%s name=%s",
            ctx.identity.run_id,
            ctx.identity.execution_attempt,
            span_name,
        )
