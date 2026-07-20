"""解析派发层的生产结果、错误码与资源预算。"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ParseErrorCode(str, Enum):
    """对 API、worker 和持久化稳定公开的解析错误码。"""

    UNSUPPORTED_TYPE = "unsupported_type"
    PARSE_FAILED = "parse_failed"
    TIMEOUT = "timeout"
    TOO_LARGE = "too_large"
    EMPTY_CONTENT = "empty_content"
    ENGINE_UNAVAILABLE = "engine_unavailable"
    UNSAFE_URL = "unsafe_url"


class ParseDispatchError(RuntimeError):
    """兼容文本接口无法返回结构化失败时抛出的异常。"""

    def __init__(self, error_code: ParseErrorCode, message: str) -> None:
        self.error_code = error_code
        super().__init__(message)


@dataclass(frozen=True)
class ParseLimits:
    """单次解析允许使用的全局资源预算。"""

    max_file_bytes: int
    max_output_chars: int
    max_total_image_bytes: int


class ParseResult(BaseModel):
    """dispatch 返回给生产消费方的完整结果。"""

    content: str = ""
    images: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    engine: str
    error_code: ParseErrorCode | None = None
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.error_code is None


def map_legacy_error(value: object) -> ParseErrorCode:
    """把现有 parser 的 metadata.error 收敛为稳定错误码。"""

    message = str(value or "").strip().lower()
    if message.startswith(("unsupported_file_type", "legacy_ppt_not_supported")):
        return ParseErrorCode.UNSUPPORTED_TYPE
    if message.startswith(("dependency_unavailable", "no_doc_tool")):
        return ParseErrorCode.ENGINE_UNAVAILABLE
    if "too_large" in message or "zip_bomb" in message:
        return ParseErrorCode.TOO_LARGE
    if message.startswith("unsafe_url"):
        return ParseErrorCode.UNSAFE_URL
    if message == "empty_result":
        return ParseErrorCode.EMPTY_CONTENT
    return ParseErrorCode.PARSE_FAILED
