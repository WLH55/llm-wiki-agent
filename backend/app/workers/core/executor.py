"""Dramatiq 消息执行器：领取 Run、驱动 handler、原子提交结果。"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.task_runtime import ProcessingRun
from app.workers.core.constants import (
    ErrorCode,
    SpanStatus,
)
from app.workers.core.errors import (
    TerminalTaskError,
    TransientTaskError,
)
from app.workers.core.runtime import (
    claim_run,
    complete_run,
    finish_worker_attempt,
    release_run,
    start_worker_attempt,
)
from app.workers.core.schemas import ExecutionOutcome

logger = logging.getLogger(__name__)

SuccessWriter = Callable[[AsyncSession, "RunExecutionContext"], Awaitable[None]]
RunHandler = Callable[["RunExecutionContext"], Awaitable[None]]


@dataclass(frozen=True)
class RunIdentity:
    """脱离 ORM 会话后仍可安全传递的 Run 身份快照。"""

    run_id: int
    tenant_id: int
    kb_id: int
    run_type: str
    scope_type: str
    scope_id: int
    attempt_no: int
    execution_attempt: int
    options_snapshot: dict[str, Any]


class RunExecutionContext:
    """业务 Handler 的执行凭证和原子成功提交入口。"""

    def __init__(
        self,
        *,
        identity: RunIdentity,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self.identity = identity
        self.session_factory = session_factory
        self.committed = False

    @property
    def run_id(self) -> int:
        return self.identity.run_id

    async def commit_success(self, writer: SuccessWriter | None = None) -> None:
        """原子提交业务结果和 Run 成功状态，失败时整笔事务回滚。"""
        if self.committed:
            raise RuntimeError(f"run {self.run_id} was already committed")
        async with self.session_factory() as db:
            async with db.begin():
                if writer is not None:
                    await writer(db, self)
                if not await complete_run(db, self.run_id):
                    raise RuntimeError(
                        f"run {self.run_id} not in running state during commit"
                    )
        self.committed = True


async def execute_run_message(
    run_id: int,
    *,
    worker_id: str,
    handlers: Mapping[str, RunHandler],
    session_factory: async_sessionmaker[AsyncSession],
) -> ExecutionOutcome:
    """消费一条身份消息；重复投递通过原子领取直接吸收。

    Dramatiq 模式下：
    - 心跳：删（span 心跳由 handler 主动调用 begin_span/end_span）
    - 退避/重试：删（Dramatiq Retries middleware 接管）
    - fencing：删（claim_run 只 CAS status）
    handler 抛异常时冒泡给 Dramatiq，由 Retries middleware 决定是否重试。
    """
    async with session_factory() as db:
        async with db.begin():
            run = await db.get(ProcessingRun, run_id)
            if run is None:
                logger.warning("忽略不存在的 Run 消息: run_id=%s", run_id)
                return ExecutionOutcome.IGNORED
            claimed = await claim_run(db, run_id)
            if not claimed:
                return ExecutionOutcome.IGNORED
            attempt_span = await start_worker_attempt(db, run, worker_id=worker_id)
            identity = RunIdentity(
                run_id=run.id,
                tenant_id=run.tenant_id,
                kb_id=run.kb_id,
                run_type=run.run_type,
                scope_type=run.scope_type,
                scope_id=run.scope_id,
                attempt_no=run.attempt_no,
                execution_attempt=attempt_span.attempt_no,
                options_snapshot=dict(run.options_snapshot or {}),
            )
            span_id = attempt_span.id

    context = RunExecutionContext(
        identity=identity,
        session_factory=session_factory,
    )
    try:
        handler = handlers.get(identity.run_type)
        if handler is None:
            raise TerminalTaskError(
                ErrorCode.UNKNOWN_RUN_TYPE, f"no handler registered for {identity.run_type}"
            )
        await handler(context)
        if not context.committed:
            raise TerminalTaskError(
                ErrorCode.HANDLER_CONTRACT_VIOLATION,
                f"handler {identity.run_type} returned without commit_success",
            )
    except asyncio.CancelledError:
        async with session_factory() as db:
            async with db.begin():
                await finish_worker_attempt(db, span_id, status=SpanStatus.CANCELLED)
        raise
    except TerminalTaskError as exc:
        # 终态错误：只记 span 失败，不标 Run 终态。
        # 异常冒泡给 Dramatiq：throws -> message.fail() -> DLQ，
        # 由 RunFailureMiddleware 标 Run failed。
        async with session_factory() as db:
            async with db.begin():
                await finish_worker_attempt(
                    db,
                    span_id,
                    status=SpanStatus.FAILED,
                    error_code=exc.error_code,
                    error_message=exc.message,
                )
        raise
    except Exception as exc:
        transient = (
            exc
            if isinstance(exc, TransientTaskError)
            else TransientTaskError(ErrorCode.UNEXPECTED_EXCEPTION, str(exc))
        )
        # 瞬态错误：记 span 失败 + 释放 Run 回 pending（重投消息可再次 claim），
        # 异常冒泡给 Dramatiq Retries middleware 决定退避重试。
        async with session_factory() as db:
            async with db.begin():
                await finish_worker_attempt(
                    db,
                    span_id,
                    status=SpanStatus.FAILED,
                    error_code=transient.error_code,
                    error_message=transient.message,
                )
                await release_run(db, run_id)
        raise transient

    async with session_factory() as db:
        async with db.begin():
            await finish_worker_attempt(db, span_id, status=SpanStatus.SUCCEEDED)
    return ExecutionOutcome.SUCCEEDED
