"""
统一响应模型模块
"""
from typing import Optional, Any, TypeVar, Generic
from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应格式"""

    code: int = Field(200, description="响应码")
    message: str = Field("success", description="响应消息")
    data: Optional[T] = Field(None, description="响应数据")

    @classmethod
    def success(cls, data: Any = None, message: str = "success") -> "ApiResponse[T]":
        """成功响应"""
        return cls(code=200, message=message, data=data)

    @classmethod
    def error(cls, code: int, message: str, data: Any = None) -> "ApiResponse[T]":
        """错误响应"""
        return cls(code=code, message=message, data=data)


class PageResponse(BaseModel, Generic[T]):
    """分页响应模型"""

    items: list[T] = Field(..., description="数据列表")
    total: int = Field(..., description="总数")
    page: int = Field(..., description="当前页码")
    page_size: int = Field(..., description="每页大小")
    total_pages: int = Field(..., description="总页数")

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PageResponse[T]":
        """创建分页响应"""
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


class ResponseCode:
    """响应码常量（HTTP 标准错误码）"""

    # 成功
    SUCCESS = 200
    CREATED = 201

    # 客户端错误
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    CONFLICT = 409

    # 服务器错误
    INTERNAL_ERROR = 500
    SERVICE_UNAVAILABLE = 503
