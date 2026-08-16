"""Dramatiq actor 注册、Run Handler 注册表与入队适配器。

同函数多 actor 注册（方案 C）：process_run_default + process_run_critical
两个 actor 共享同一份执行逻辑，仅 queue_name 不同，实现 critical/default 队列路由。
"""

import importlib
from typing import TYPE_CHECKING

import dramatiq

from app.config import settings
from app.workers.core.constants import CRITICAL_QUEUE, CRITICAL_RUN_TYPES, DEFAULT_QUEUE
from app.workers.core.database import worker_session_factory
from app.workers.core.errors import TerminalTaskError
from app.workers.core.executor import execute_run_message

if TYPE_CHECKING:
    from app.workers.core.executor import RunHandler


RUN_HANDLERS: dict[str, "RunHandler"] = {}

# 显式 handler 模块清单（新增 handler 时加一行路径）
HANDLER_MODULES = [
    "app.knowledge_bases.service.rag_ingestion",
    # 未来: "app.knowledge_bases.service.wiki_generate",
]


def register_run_handler(run_type: str):
    """业务 handler 注册装饰器，由各领域 service 模块使用。"""

    def decorator(handler: "RunHandler") -> "RunHandler":
        RUN_HANDLERS[run_type] = handler
        return handler

    return decorator


_handlers_loaded: bool = False


def _load_handlers() -> None:
    """加载显式清单中的 handler 模块（首次调用后置标志，避免重复遍历）。

    不在 __init__.py 模块 import 时调用，避免循环导入
   （rag_ingestion 会 from app.workers import ... 导致 partially initialized module）。
    由 actor 首次执行时惰性触发，或测试显式调用。
    """
    global _handlers_loaded
    if _handlers_loaded:
        return
    for module_path in HANDLER_MODULES:
        importlib.import_module(module_path)
    _handlers_loaded = True


# 同函数多 actor 注册（方案 C）：critical / default 两个队列入口
@dramatiq.actor(
    queue_name=DEFAULT_QUEUE,
    max_retries=3,
    min_backoff=5000,
    max_backoff=300000,
    time_limit=settings.TASK_TIME_LIMIT_MS,
    throws=(TerminalTaskError,),
)
async def process_run_default(run_id: int) -> str:
    """default 队列入口：处理 document_process / wiki_generate 等。"""
    _load_handlers()
    outcome = await execute_run_message(
        run_id,
        worker_id="default",
        handlers=RUN_HANDLERS,
        session_factory=worker_session_factory,
    )
    return outcome.value


@dramatiq.actor(
    queue_name=CRITICAL_QUEUE,
    max_retries=3,
    min_backoff=5000,
    max_backoff=300000,
    time_limit=settings.TASK_TIME_LIMIT_MS,
    throws=(TerminalTaskError,),
)
async def process_run_critical(run_id: int) -> str:
    """critical 队列入口：处理 rag_index / source_sync 等。"""
    _load_handlers()
    outcome = await execute_run_message(
        run_id,
        worker_id="critical",
        handlers=RUN_HANDLERS,
        session_factory=worker_session_factory,
    )
    return outcome.value


def enqueue_run(run_type: str, run_id: int) -> None:
    """按 run_type 选 actor 入队。critical -> process_run_critical；其余 -> process_run_default。"""
    if run_type in CRITICAL_RUN_TYPES:
        process_run_critical.send(run_id)
    else:
        process_run_default.send(run_id)
