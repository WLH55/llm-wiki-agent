"""Parser 模块内部异常。"""

from app.parsers.core.schemas import ParseErrorCode


class ParserError(RuntimeError):
    """携带稳定错误码的 parser 基础异常。"""

    def __init__(self, error_code: ParseErrorCode, message: str) -> None:
        self.error_code = error_code
        super().__init__(message)


class ParseDispatchError(ParserError):
    """兼容文本接口无法返回结构化失败时抛出的异常。"""


class ParserAssetError(ParserError):
    """解析派生资产解码或持久化失败。"""
