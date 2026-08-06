"""Workers 包：异步执行基础设施（Dramatiq 消费、Run 状态机、Span 心跳）。

公开 API：
- 队列常量：`DEFAULT_QUEUE` / `CRITICAL_QUEUE`
- Run 创建与入队：`create_run` / `enqueue_run`
- Handler 注册：`register_run_handler` / `RUN_HANDLERS`
- 执行上下文（业务 handler 需要）：`RunExecutionContext` / `RunIdentity`
- 错误类型（业务 handler 需要）：`ExecutionOutcome` / `TaskExecutionError` / `TransientTaskError` / `TerminalTaskError`
- Span 心跳（业务 handler 需要）：`begin_span` / `end_span` / `fail_span` / `skip_span`
"""

from app.workers.core.broker import broker  # noqa: F401 -- 触发 broker + middleware 初始化
from app.workers.core.constants import (
    CRITICAL_QUEUE,
    DEFAULT_QUEUE,
    ErrorCode,
    RunStatus,
    RunType,
    ScopeType,
    SpanName,
    SpanStatus,
    TriggerType,
)
from app.workers.core.errors import (
    TaskExecutionError,
    TerminalTaskError,
    TransientTaskError,
)
from app.workers.core.executor import RunExecutionContext, RunIdentity
from app.workers.core.runtime import create_run, mark_run_enqueue_failed
from app.workers.core.schemas import ExecutionOutcome
from app.workers.core.span_tracker import begin_span, end_span, fail_span, skip_span
from app.workers.core.tasks import (
    RUN_HANDLERS,
    enqueue_run,
    register_run_handler,
)

__all__ = [
    "DEFAULT_QUEUE",
    "CRITICAL_QUEUE",
    "create_run",
    "enqueue_run",
    "mark_run_enqueue_failed",
    "register_run_handler",
    "RUN_HANDLERS",
    "RunExecutionContext",
    "RunIdentity",
    "ExecutionOutcome",
    "TaskExecutionError",
    "TransientTaskError",
    "TerminalTaskError",
    "begin_span",
    "end_span",
    "fail_span",
    "skip_span",
    # 常量与枚举
    "RunStatus",
    "SpanStatus",
    "RunType",
    "ScopeType",
    "TriggerType",
    "ErrorCode",
    "SpanName",
]