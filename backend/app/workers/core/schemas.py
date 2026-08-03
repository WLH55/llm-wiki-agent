"""Workers 数据契约：执行结果状态码等跨模块共享的纯数据定义。"""

from enum import StrEnum


class ExecutionOutcome(StrEnum):
    """一条至少一次投递消息的业务处理结果。"""

    IGNORED = "ignored"
    SUCCEEDED = "succeeded"
    RETRY_SCHEDULED = "retry_scheduled"
    FAILED = "failed"
