"""Outbox Publisher 独立进程入口。"""

import asyncio
import signal

from app.config import settings
from app.config.logging import setup_logging
from app.models.database import async_session_factory
from app.workers.outbox_service import run_outbox_service
from app.workers.tasks import send_task_message


def _install_shutdown_handlers(stop: asyncio.Event) -> None:
    """容器退出时停止领取新 Outbox，并让当前发布循环自然收尾。"""
    loop = asyncio.get_running_loop()
    for shutdown_signal in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(shutdown_signal, stop.set)
        except (NotImplementedError, RuntimeError):
            # Windows 和非主线程事件循环不支持 signal handler。
            pass


async def run() -> None:
    """持续发布 Outbox，并周期性补偿遗失的 Run 投递。"""
    stop = asyncio.Event()
    _install_shutdown_handlers(stop)
    await run_outbox_service(
        session_factory=async_session_factory,
        sender=send_task_message,
        stop=stop,
        batch_size=settings.TASK_OUTBOX_BATCH_SIZE,
        lock_seconds=settings.TASK_OUTBOX_LOCK_SECONDS,
        poll_seconds=settings.TASK_OUTBOX_POLL_SECONDS,
        retry_base_seconds=settings.TASK_RETRY_BASE_SECONDS,
        retry_max_seconds=settings.TASK_RETRY_MAX_SECONDS,
        reaper_interval_seconds=30,
        stale_after_seconds=settings.TASK_LEASE_SECONDS,
    )


def main() -> None:
    """供容器命令 `python -m app.workers.outbox_worker` 调用。"""
    setup_logging()
    asyncio.run(run())


if __name__ == "__main__":
    main()
