"""Workers 异常类：带稳定机器错误码的可分类任务错误。"""


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
