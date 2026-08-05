"""Dramatiq middleware：RunFailureMiddleware + ReaperMiddleware。

- RunFailureMiddleware：消息处理失败时标 Run failed（executor _handle_failure 的兜底）
- ReaperMiddleware：after_process_boot 启 Reaper 线程，before_worker_shutdown 停止
"""

import asyncio
import logging
import threading

from dramatiq.asyncio import get_event_loop_thread
from dramatiq.middleware import Middleware

from app.workers.core.constants import ErrorCode
from app.workers.core.reaper import run_reaper_loop
from app.workers.core.runtime import fail_run

logger = logging.getLogger(__name__)


def _run_coroutine_safely(coro):
    """在 EventLoopThread 的 loop 上执行协程；loop 不可用时退回 asyncio.run。

    worker 进程中 AsyncIO middleware 的 before_worker_boot 已启动 EventLoopThread，
    复用它可保证 asyncpg 连接池与 actor 共用同一个 loop，避免跨 loop 报错。
    非 worker 上下文（如测试）EventLoopThread 为 None，退回 asyncio.run 兜底。
    """
    loop_thread = get_event_loop_thread()
    if loop_thread is not None:
        return loop_thread.run_coroutine(coro)
    return asyncio.run(coro)


class RunFailureMiddleware(Middleware):
    """after_process_message 钩子：消息失败时标 Run failed。

    作为 executor._handle_failure 的兜底：处理 executor 自身抛异常的情况
    （如 claim_run / start_worker_attempt / commit_success 的 DB 错误）。
    executor 内部已标 Run failed 的，fail_run 的 CAS running->failed 返回 False，幂等。
    """

    def __init__(self, session_factory) -> None:
        super().__init__()
        self.session_factory = session_factory

    def after_process_message(self, broker, message, *, result=None, exception=None) -> None:
        if exception is None:
            return
        run_id = message.args[0] if message.args else None
        if run_id is None:
            return
        try:
            _run_coroutine_safely(self._mark_failed(run_id, str(exception)))
        except Exception:
            logger.exception(
                "RunFailureMiddleware failed to mark run failed: run_id=%s", run_id
            )

    async def _mark_failed(self, run_id: int, error_message: str) -> None:
        async with self.session_factory() as db:
            async with db.begin():
                await fail_run(
                    db,
                    run_id,
                    error_code=ErrorCode.MIDDLEWARE_FAILURE,
                    error_message=error_message[:1000],
                )


class ReaperMiddleware(Middleware):
    """after_process_boot 启 Reaper 线程；before_worker_shutdown 停止。

    每个 worker 子进程启动一个 Reaper 线程，定期扫描卡死 Run。
    """

    def __init__(
        self,
        session_factory,
        *,
        interval_seconds: float,
        span_stale_seconds: float,
        pending_stale_seconds: float,
    ) -> None:
        super().__init__()
        self.session_factory = session_factory
        self.interval_seconds = interval_seconds
        self.span_stale_seconds = span_stale_seconds
        self.pending_stale_seconds = pending_stale_seconds
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def after_process_boot(self, broker) -> None:
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=run_reaper_loop,
            kwargs={
                "session_factory": self.session_factory,
                "interval_seconds": self.interval_seconds,
                "span_stale_seconds": self.span_stale_seconds,
                "pending_stale_seconds": self.pending_stale_seconds,
                "stop": self._stop_event,
            },
            daemon=True,
            name="reaper-loop",
        )
        self._thread.start()
        logger.info("ReaperMiddleware started reaper thread")

    def before_worker_shutdown(self, broker) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=30)
        logger.info("ReaperMiddleware stopped reaper thread")
