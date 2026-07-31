"""Taskiq 消息执行器：领取 Run、维护租约并驱动可靠状态转换。"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.task_runtime import ProcessingRun
from app.workers.broker import CRITICAL_QUEUE, DEFAULT_QUEUE, LOW_QUEUE
from app.workers.runtime import (
    ExecutionLease,
    claim_run,
    complete_run,
    fail_run,
    finish_worker_attempt,
    renew_lease,
    retry_run,
    start_worker_attempt,
)

logger = logging.getLogger(__name__)

SuccessWriter = Callable[[AsyncSession, "RunExecutionContext"], Awaitable[None]]
RunHandler = Callable[["RunExecutionContext"], Awaitable[None]]
RetryJitter = Callable[[float], float]


class ExecutionOutcome(StrEnum):
    """一条至少一次投递消息的业务处理结果。"""

    IGNORED = "ignored"
    SUCCEEDED = "succeeded"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"


class TaskExecutionError(Exception):
    """带稳定机器错误码的可分类任务错误。"""

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


class TransientTaskError(TaskExecutionError):
    """可以在自动重试预算内再次执行的瞬时错误。"""


class TerminalTaskError(TaskExecutionError):
    """重试不会自行恢复的业务终态错误。"""


class LeaseLostError(TaskExecutionError):
    """当前 Worker 已不再拥有 Run 的提交权。"""

    def __init__(self, message: str = "execution lease lost"):
        super().__init__("lease_lost", message)


@dataclass(frozen=True)
class RunIdentity:
    """脱离 ORM 会话后仍可安全传递的 Run 身份快照。"""

    run_id: int
    tenant_id: int
    kb_id: int
    run_type: str
    scope_type: str
    scope_id: int
    options_snapshot: dict[str, Any]


class RunExecutionContext:
    """业务 Handler 的执行凭证和原子成功提交入口。"""

    def __init__(
        self,
        *,
        identity: RunIdentity,
        lease: ExecutionLease,
        session_factory: async_sessionmaker[AsyncSession],
        lease_seconds: float,
    ) -> None:
        self.identity = identity
        self.lease = lease
        self.session_factory = session_factory
        self.lease_seconds = lease_seconds
        self.committed = False
        self._lease_lock = asyncio.Lock()

    @property
    def run_id(self) -> int:
        return self.identity.run_id

    async def renew(self) -> bool:
        """使用独立短事务续租，避免长业务阶段占用数据库事务。"""
        async with self._lease_lock:
            async with self.session_factory() as db:
                async with db.begin():
                    renewed = await renew_lease(
                        db,
                        self.lease,
                        lease_seconds=self.lease_seconds,
                    )
            if renewed is None:
                return False
            self.lease = renewed
            return True

    async def commit_success(self, writer: SuccessWriter | None = None) -> None:
        """原子提交业务结果和 Run 成功状态，失败时整笔事务回滚。"""
        async with self._lease_lock:
            if self.committed:
                raise RuntimeError(f"run {self.run_id} was already committed")
            async with self.session_factory() as db:
                async with db.begin():
                    if writer is not None:
                        await writer(db, self)
                    if not await complete_run(db, self.lease):
                        raise LeaseLostError(
                            f"run {self.run_id} lease expired before result commit"
                        )
            self.committed = True


def queue_name_for_run(run_type: str) -> str:
    """把业务 Run 类型映射到稳定 Redis Stream；优先级不进入消息正文。"""
    if run_type in {"rag_index", "source_sync"}:
        return CRITICAL_QUEUE
    if run_type == "wiki_generate":
        return LOW_QUEUE
    return DEFAULT_QUEUE


def _retry_delay(
    attempt: int,
    *,
    base_seconds: float,
    max_seconds: float,
    jitter: RetryJitter,
) -> float:
    raw_delay = min(max_seconds, base_seconds * (2 ** max(0, attempt - 1)))
    return max(0.0, raw_delay + jitter(raw_delay))


def _default_jitter(delay: float) -> float:
    return random.uniform(0, delay * 0.2) if delay > 0 else 0


async def _heartbeat_loop(
    context: RunExecutionContext,
    *,
    interval_seconds: float,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            return
        except TimeoutError:
            if not await context.renew():
                logger.warning("Run 租约续期失败，停止心跳: run_id=%s", context.run_id)
                return


async def _stop_heartbeat(task: asyncio.Task[None], stop: asyncio.Event) -> None:
    stop.set()
    await task


async def _finish_cancelled_attempt(
    session_factory: async_sessionmaker[AsyncSession],
    span_id: int,
) -> None:
    async with session_factory() as db:
        async with db.begin():
            await finish_worker_attempt(db, span_id, status="cancelled")


async def _handle_failure(
    *,
    context: RunExecutionContext,
    span_id: int,
    attempt: int,
    error: TaskExecutionError,
    terminal: bool,
    session_factory: async_sessionmaker[AsyncSession],
    max_auto_retries: int,
    retry_base_seconds: float,
    retry_max_seconds: float,
    retry_jitter: RetryJitter,
) -> ExecutionOutcome:
    should_retry = not terminal and attempt <= max_auto_retries
    transition_succeeded = False
    async with session_factory() as db:
        async with db.begin():
            await finish_worker_attempt(
                db,
                span_id,
                status="failed",
                error_code=error.error_code,
                error_message=error.message,
            )
            if should_retry:
                delay = _retry_delay(
                    attempt,
                    base_seconds=retry_base_seconds,
                    max_seconds=retry_max_seconds,
                    jitter=retry_jitter,
                )
                transition_succeeded = await retry_run(
                    db,
                    context.lease,
                    queue_name=queue_name_for_run(context.identity.run_type),
                    available_at=datetime.now(timezone.utc) + timedelta(seconds=delay),
                    error_code=error.error_code,
                )
            else:
                transition_succeeded = await fail_run(
                    db,
                    context.lease,
                    error_code=error.error_code,
                    error_message=error.message,
                )
    if not transition_succeeded:
        raise LeaseLostError(f"run {context.run_id} was taken over during failure handling")
    return (
        ExecutionOutcome.RETRY_SCHEDULED
        if should_retry
        else ExecutionOutcome.FAILED
    )


async def execute_run_message(
    run_id: int,
    *,
    worker_id: str,
    handlers: Mapping[str, RunHandler],
    session_factory: async_sessionmaker[AsyncSession],
    lease_seconds: float = 900,
    heartbeat_seconds: float = 15,
    max_auto_retries: int = 3,
    retry_base_seconds: float = 5,
    retry_max_seconds: float = 300,
    retry_jitter: RetryJitter = _default_jitter,
) -> ExecutionOutcome:
    """消费一条身份消息；重复投递通过原子领取直接吸收。"""
    async with session_factory() as db:
        async with db.begin():
            run = await db.get(ProcessingRun, run_id)
            if run is None:
                logger.warning("忽略不存在的 Run 消息: run_id=%s", run_id)
                return ExecutionOutcome.IGNORED
            lease = await claim_run(
                db,
                run_id,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )
            if lease is None:
                return ExecutionOutcome.IGNORED
            attempt_span = await start_worker_attempt(db, run, lease)
            identity = RunIdentity(
                run_id=run.id,
                tenant_id=run.tenant_id,
                kb_id=run.kb_id,
                run_type=run.run_type,
                scope_type=run.scope_type,
                scope_id=run.scope_id,
                options_snapshot=dict(run.options_snapshot or {}),
            )
            attempt = int(attempt_span.metrics["attempt"])
            span_id = attempt_span.id

    context = RunExecutionContext(
        identity=identity,
        lease=lease,
        session_factory=session_factory,
        lease_seconds=lease_seconds,
    )
    stop_heartbeat = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        _heartbeat_loop(
            context,
            interval_seconds=heartbeat_seconds,
            stop=stop_heartbeat,
        )
    )
    try:
        handler = handlers.get(identity.run_type)
        if handler is None:
            raise TerminalTaskError(
                "unknown_run_type", f"no handler registered for {identity.run_type}"
            )
        await handler(context)
        if not context.committed:
            raise TerminalTaskError(
                "handler_contract_violation",
                f"handler {identity.run_type} returned without commit_success",
            )
    except asyncio.CancelledError:
        await _stop_heartbeat(heartbeat_task, stop_heartbeat)
        await _finish_cancelled_attempt(session_factory, span_id)
        raise
    except LeaseLostError:
        await _stop_heartbeat(heartbeat_task, stop_heartbeat)
        async with session_factory() as db:
            async with db.begin():
                await finish_worker_attempt(
                    db,
                    span_id,
                    status="failed",
                    error_code="lease_lost",
                    error_message="execution lease lost before commit",
                )
        raise
    except TerminalTaskError as exc:
        await _stop_heartbeat(heartbeat_task, stop_heartbeat)
        return await _handle_failure(
            context=context,
            span_id=span_id,
            attempt=attempt,
            error=exc,
            terminal=True,
            session_factory=session_factory,
            max_auto_retries=max_auto_retries,
            retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds,
            retry_jitter=retry_jitter,
        )
    except Exception as exc:
        await _stop_heartbeat(heartbeat_task, stop_heartbeat)
        transient = (
            exc
            if isinstance(exc, TransientTaskError)
            else TransientTaskError("unexpected_exception", str(exc))
        )
        return await _handle_failure(
            context=context,
            span_id=span_id,
            attempt=attempt,
            error=transient,
            terminal=False,
            session_factory=session_factory,
            max_auto_retries=max_auto_retries,
            retry_base_seconds=retry_base_seconds,
            retry_max_seconds=retry_max_seconds,
            retry_jitter=retry_jitter,
        )

    await _stop_heartbeat(heartbeat_task, stop_heartbeat)
    async with session_factory() as db:
        async with db.begin():
            await finish_worker_attempt(db, span_id, status="succeeded")
    return ExecutionOutcome.SUCCEEDED
