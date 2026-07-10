"""
Auth 相关 schemas
"""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求"""
    email: str = Field(..., description="邮箱")
    password: str = Field(..., min_length=1, max_length=128, description="密码")


class TokenResponse(BaseModel):
    """登录响应"""
    access_token: str
    token_type: str = "bearer"
    expires_in_hours: int = 24


class UserResponse(BaseModel):
    """用户信息"""
    id: int
    email: str
    role: str
    tenant_id: int

    model_config = {"from_attributes": True}
