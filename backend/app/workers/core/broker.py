"""Dramatiq RedisBroker 与队列定义。

队列拓扑简化为 critical + default（删 multimodal/low）。
broker 在模块 import 时初始化，dramatiq.set_broker 注册为全局 broker，
之后 @dramatiq.actor 装饰器会使用这个 broker。
"""

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import AsyncIO, Retries

from app.config import settings
from app.models.database import async_session_factory
from app.workers.core.middleware import ReaperMiddleware, RunFailureMiddleware

# 全局 broker 实例（模块 import 时由 create_broker 初始化）
broker: RedisBroker | None = None


def create_broker(redis_url: str) -> RedisBroker:
    """构造 Dramatiq RedisBroker，注册 AsyncIO + RunFailure + Reaper 中间件。"""
    b = RedisBroker(url=redis_url)
    # AsyncIO middleware：让 async actor 能在 worker 线程中运行
    b.add_middleware(AsyncIO())
    # RunFailure middleware：消息最终死亡时标 Run failed（失败回调）
    # 注册在 Retries 之前：emit_after 按逆序执行，保证本钩子在 Retries 之后运行，
    # 才能读到 message.failed 的最终判定（throws / 重试耗尽）。
    b.add_middleware(
        RunFailureMiddleware(session_factory=async_session_factory),
        before=Retries,
    )
    # Reaper middleware：after_process_boot 启 Reaper 线程
    b.add_middleware(
        ReaperMiddleware(
            session_factory=async_session_factory,
            interval_seconds=settings.TASK_REAPER_INTERVAL_SECONDS,
            span_stale_seconds=settings.TASK_SPAN_STALE_SECONDS,
            pending_stale_seconds=settings.TASK_PENDING_STALE_SECONDS,
        )
    )
    return b


# 模块 import 时初始化全局 broker 并注册到 dramatiq
broker = create_broker(settings.REDIS_URL)
dramatiq.set_broker(broker)
