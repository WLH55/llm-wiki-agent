"""Parser 模块的数据契约。"""

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


@dataclass(frozen=True)
class ParseLimits:
    """单次解析允许使用的全局资源预算。"""

    max_file_bytes: int
    max_output_chars: int
    max_total_image_bytes: int


class ParseResult(BaseModel):
    """派发服务返回给生产消费方的完整结果。"""

    content: str = ""
    images: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    engine: str
    error_code: ParseErrorCode | None = None
    warnings: list[str] = Field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return self.error_code is None
