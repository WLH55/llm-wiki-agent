"""
Auth 路由：POST /api/auth/login、GET /api/auth/me

路由层职责：参数校验 + 调 service；不写 try/except。
"""
from fastapi import APIRouter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import create_access_token
from app.auth.password import verify_password
from app.config.exceptions import BusinessValidationException
from app.config.schemas import ApiResponse
from app.deps import CurrentUserDep, DbDep
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["鉴权"])


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(payload: LoginRequest, db: DbDep) -> ApiResponse[TokenResponse]:
    """邮箱 + 密码 → JWT"""
    result = await db.execute(
        select(User).where(User.email == payload.email).limit(1)
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise BusinessValidationException("邮箱或密码错误")
    if not user.is_active or user.deleted_at is not None:
        raise BusinessValidationException("用户已禁用")

    token = create_access_token(user.id)
    return ApiResponse.success(
        data=TokenResponse(
            access_token=token,
            expires_in_hours=24,
        )
    )


@router.get("/me", response_model=ApiResponse[UserResponse])
async def get_me(user: CurrentUserDep) -> ApiResponse[UserResponse]:
    """获取当前用户信息"""
    return ApiResponse.success(
        data=UserResponse(
            id=user.id,
            email=user.email,
            role=user.role,
            tenant_id=user.tenant_id,
        )
    )
