"""Workers 包：异步执行基础设施（Taskiq 消费、Outbox 可靠投递、Run 状态机）。

公开 API：
- 队列常量：`DEFAULT_QUEUE` / `CRITICAL_QUEUE` / `LOW_QUEUE` / `MULTIMODAL_QUEUE`
- Run 创建：`create_run_with_outbox`
- Handler 注册：`register_run_handler` / `RUN_HANDLERS` / `load_handlers`
- 执行上下文（业务 handler 需要）：`RunExecutionContext` / `RunIdentity`
- 错误类型（业务 handler 需要）：`ExecutionOutcome` / `TaskExecutionError` / `TransientTaskError` / `TerminalTaskError` / `LeaseLostError`
- 发送适配器：`send_task_message`
"""

from app.workers.core.broker import (
    CRITICAL_QUEUE,
    DEFAULT_QUEUE,
    LOW_QUEUE,
    MULTIMODAL_QUEUE,
)
from app.workers.core.errors import (
    LeaseLostError,
    TaskExecutionError,
    TerminalTaskError,
    TransientTaskError,
)
from app.workers.core.executor import RunExecutionContext, RunIdentity
from app.workers.core.runtime import create_run_with_outbox
from app.workers.core.schemas import ExecutionOutcome
from app.workers.core.tasks import (
    RUN_HANDLERS,
    register_run_handler,
    send_task_message,
)

__all__ = [
    "DEFAULT_QUEUE",
    "CRITICAL_QUEUE",
    "LOW_QUEUE",
    "MULTIMODAL_QUEUE",
    "create_run_with_outbox",
    "register_run_handler",
    "RUN_HANDLERS",
    "load_handlers",
    "RunExecutionContext",
    "RunIdentity",
    "ExecutionOutcome",
    "TaskExecutionError",
    "TransientTaskError",
    "TerminalTaskError",
    "LeaseLostError",
    "send_task_message",
]


def load_handlers() -> None:
    """显式触发 handler 模块加载；测试与进程启动时调用。"""
    from app.workers.core.tasks import _load_handlers
    _load_handlers()


# 模块加载完成后触发 handler 注册；此时 app.workers 公开符号已就绪，
# 领域 service 的 `from app.workers import ...` 可正常解析，避免循环导入。
load_handlers()
