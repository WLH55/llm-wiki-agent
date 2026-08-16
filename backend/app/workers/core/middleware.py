"""Dramatiq middleware：RunFailureMiddleware + ReaperMiddleware。

- RunFailureMiddleware：消息最终死亡时标 Run failed（异常冒泡后由 Retries 判定，
-   message.failed=True 才标记；必须注册在 Retries 之前，逆序链中位于其后）
- ReaperMiddleware：after_process_boot 启 Reaper 线程，before_worker_shutdown 停止
"""

import logging
import threading

from dramatiq.asyncio import get_event_loop_thread
from dramatiq.middleware import Middleware

from app.workers.core.constants import ErrorCode, RunStatus
from app.workers.core.reaper import run_reaper_loop
from app.workers.core.runtime import fail_run

logger = logging.getLogger(__name__)


def _run_coroutine_safely(coro):
    """在 EventLoopThread 的 loop 上执行协程并同步等待结果。

    worker 进程中 AsyncIO middleware 的 before_worker_boot 已启动 EventLoopThread，
    actor 与本函数共用同一个 loop，保证 asyncpg 连接池不跨 loop 复用。
    EventLoopThread 不存在说明不在 worker 上下文，直接报错——
    asyncio.run 会创建临时 loop，连接绑定后被销毁的 loop，污染共享池。
    """
    loop_thread = get_event_loop_thread()
    if loop_thread is None:
        raise RuntimeError(
            "EventLoopThread 未启动：worker 会话只能在 dramatiq worker 进程内使用"
        )
    return loop_thread.run_coroutine(coro)


class RunFailureMiddleware(Middleware):
    """after_process_message 钩子：消息最终死亡时标 Run failed。

    executor 现在让异常冒泡给 Dramatiq，本 middleware 是失败回调：
    只有 Retries 判定"放弃"（throws 终态错误 / 重试耗尽，message.failed=True）
    才标 Run failed；Retries 安排了下次重试时不标，等重投消息再次 claim。
    必须通过 add_middleware(..., before=Retries) 注册，保证逆序链中本钩子
    在 Retries 之后执行，才能读到 message.failed 的最终判定。
    """

    def __init__(self, session_factory) -> None:
        super().__init__()
        self.session_factory = session_factory

    def after_process_message(self, broker, message, *, result=None, exception=None) -> None:
        # message.failed 由 Retries middleware 判定：
        #   True  = throws 终态错误 或 重试耗尽（即将进 DLQ）-> 标 Run failed
        #   False = Retries 已安排下一次重试 -> 不标，等重投消息再 claim
        if exception is None or not message.failed:
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
                    statuses=(RunStatus.RUNNING, RunStatus.PENDING),
                )


class ReaperMiddleware(Middleware):
    """after_process_boot 启 Reaper 线程；before_worker_shutdown 停止。

    每个 worker 子进程启动一个 Reaper 线程，定期扫描卡死 Run。
    """

    def __init__(
        self,
        *,
        dsn: str,
        interval_seconds: float,
        span_stale_seconds: float,
        pending_stale_seconds: float,
    ) -> None:
        super().__init__()
        self.dsn = dsn
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
                "dsn": self.dsn,
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
