"""
异常类定义模块
"""
import logging
from typing import Optional
from fastapi import Request, status
from starlette.responses import JSONResponse

from app.config.schemas import ApiResponse, ResponseCode

logger = logging.getLogger(__name__)


def _log_exception(
    request: Request,
    exc: Exception,
    level: str = logging.ERROR,
    include_stacktrace: bool = False
) -> None:
    """
    记录异常日志

    Args:
        request: 请求对象
        exc: 异常对象
        level: 日志级别 (ERROR, WARNING)
        include_stacktrace: 是否包含堆栈跟踪
    """
    client_ip = request.client.host if request.client else "unknown"

    log_parts = [
        f"[{client_ip}]",
        f"[{request.method}]",
        f"[{request.url.path}]",
    ]

    if request.query_params:
        log_parts.append(f"| Query: {dict(request.query_params)}")

    body = getattr(request.state, "body", None)
    if body:
        log_parts.append(f"| Body: {body}")

    if request.path_params:
        log_parts.append(f"| Path: {request.path_params}")

    exc_type = type(exc).__name__
    exc_msg = str(exc)
    log_parts.append(f"- {exc_type}: {exc_msg}")

    log_message = " ".join(log_parts)

    log_func = getattr(logger, level.lower(), logger.error)
    if include_stacktrace:
        log_func(log_message, exc_info=True)
    else:
        log_func(log_message)


class BusinessValidationException(Exception):
    """业务参数异常类"""

    def __init__(self, message: str, code: Optional[int] = None):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ResourceNotFoundException(Exception):
    """资源未找到异常"""

    def __init__(self, message: str = "资源不存在"):
        self.message = message
        super().__init__(self.message)


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理所有未捕获的异常"""
    _log_exception(request, exc, level="ERROR")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ApiResponse.error(
            code=ResponseCode.INTERNAL_ERROR,
            message=str(exc) or "服务器内部错误",
            data=None
        ).model_dump()
    )


async def validation_exception_handler(
    request: Request,
    exc: BusinessValidationException
) -> JSONResponse:
    """处理业务异常"""
    _log_exception(request, exc, level="WARNING")

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ApiResponse.error(
            code=ResponseCode.BAD_REQUEST,
            message=exc.message or "处理请求参数验证异常",
            data=None
        ).model_dump()
    )


def register_exception_handlers(app) -> None:
    """注册全局异常处理器到 FastAPI 应用"""
    app.add_exception_handler(BusinessValidationException, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
