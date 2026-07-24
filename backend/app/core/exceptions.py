"""框架无关的应用级异常。"""


class BusinessValidationException(Exception):  # noqa: N818 - 保留现有公共异常名
    """业务规则拒绝当前请求。"""

    def __init__(
        self,
        message: str,
        code: int | None = None,
        error_code: str | None = None,
    ):
        self.message = message
        self.code = code
        self.error_code = error_code
        super().__init__(self.message)


class ResourceNotFoundException(Exception):  # noqa: N818 - 保留现有公共异常名
    """请求的应用资源不存在。"""

    def __init__(self, message: str = "资源不存在"):
        self.message = message
        super().__init__(self.message)
