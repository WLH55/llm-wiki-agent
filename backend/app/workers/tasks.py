"""Taskiq 任务注册、Run Handler 注册表与 Outbox 发送适配器。"""

import os
import socket
from collections.abc import Mapping

from app.config import settings
from app.models.database import async_session_factory
from app.workers.broker import (
    CRITICAL_QUEUE,
    DEFAULT_QUEUE,
    LOW_QUEUE,
    MULTIMODAL_QUEUE,
    critical_broker,
    shared_broker,
)
from app.workers.executor import RunHandler, execute_run_message
from app.workers.rag_ingestion import document_process_handler, rag_index_handler

QUEUE_ALIASES = {
    "critical": CRITICAL_QUEUE,
    "default": DEFAULT_QUEUE,
    "multimodal": MULTIMODAL_QUEUE,
    "low": LOW_QUEUE,
    CRITICAL_QUEUE: CRITICAL_QUEUE,
    DEFAULT_QUEUE: DEFAULT_QUEUE,
    MULTIMODAL_QUEUE: MULTIMODAL_QUEUE,
    LOW_QUEUE: LOW_QUEUE,
}

RUN_HANDLERS: dict[str, RunHandler] = {
    "document_process": document_process_handler,
    "rag_index": rag_index_handler,
}


def register_run_handlers(handlers: Mapping[str, RunHandler]) -> None:
    """启动时注册应用 Run 类型；重复名称由后加载实现显式覆盖。"""
    RUN_HANDLERS.update(handlers)


def worker_identity(lane: str) -> str:
    """生成日志和租约中可定位到容器、进程及 lane 的 Worker ID。"""
    host = os.getenv("HOSTNAME") or socket.gethostname()
    return f"{host}:{os.getpid()}:{lane}"


async def _dispatch_run(run_id: int, *, lane: str) -> str:
    outcome = await execute_run_message(
        run_id,
        worker_id=worker_identity(lane),
        handlers=RUN_HANDLERS,
        session_factory=async_session_factory,
        lease_seconds=settings.TASK_LEASE_SECONDS,
        heartbeat_seconds=settings.TASK_HEARTBEAT_SECONDS,
        max_auto_retries=settings.TASK_MAX_AUTO_RETRIES,
        retry_base_seconds=settings.TASK_RETRY_BASE_SECONDS,
        retry_max_seconds=settings.TASK_RETRY_MAX_SECONDS,
    )
    return outcome.value


@shared_broker.task(task_name="process_run")
async def process_run_shared(run_id: int) -> str:
    """共享容量入口：处理 default 及其可吸收的其他 Stream。"""
    return await _dispatch_run(run_id, lane="shared")


@critical_broker.task(task_name="process_run")
async def process_run_critical(run_id: int) -> str:
    """保留容量入口：只处理 critical Stream。"""
    return await _dispatch_run(run_id, lane="critical")


async def send_task_message(task_name: str, run_id: int, queue_name: str) -> None:
    """Outbox sender：消息只传 Run ID，队列通过 Taskiq label 路由。"""
    if task_name != "process_run":
        raise ValueError(f"unknown task name: {task_name}")
    stream_name = QUEUE_ALIASES.get(queue_name)
    if stream_name is None:
        raise ValueError(f"unknown task queue: {queue_name}")
    await (
        process_run_shared.kicker()
        .with_labels(queue_name=stream_name)
        .kiq(run_id)
    )
