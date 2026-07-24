"""FastAPI 异常到响应的转换适配器。"""

import logging

from fastapi import FastAPI, Request, status
from starlette.responses import JSONResponse

from app.core.exceptions import BusinessValidationException
from app.web.schemas import ApiResponse, ResponseCode

logger = logging.getLogger(__name__)


def _log_exception(
    request: Request,
    exc: Exception,
    level: int = logging.ERROR,
    include_stacktrace: bool = False,
) -> None:
    """记录异常及其请求上下文。"""
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
    log_parts.append(f"- {type(exc).__name__}: {exc}")
    logger.log(level, " ".join(log_parts), exc_info=include_stacktrace)


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """将未捕获异常转为统一 HTTP 响应。"""
    _log_exception(request, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ApiResponse.error(
            code=ResponseCode.INTERNAL_ERROR,
            message=str(exc) or "服务器内部错误",
            data=None,
        ).model_dump(),
    )


async def validation_exception_handler(
    request: Request,
    exc: BusinessValidationException,
) -> JSONResponse:
    """将应用校验异常转为 HTTP 400。"""
    _log_exception(request, exc, level=logging.WARNING)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ApiResponse.error(
            code=ResponseCode.BAD_REQUEST,
            message=exc.message or "处理请求参数验证异常",
            data={"error_code": exc.error_code} if exc.error_code else None,
        ).model_dump(),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """向 FastAPI 应用注册全局异常处理器。"""
    app.add_exception_handler(BusinessValidationException, validation_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
