"""
Auth 路由：POST /api/auth/login、GET /api/auth/me

路由层职责：参数校验 + 调 service；不写 try/except。
"""
from fastapi import APIRouter

from app.auth.api.dependencies import CurrentUserDep
from app.auth.api.schemas import LoginRequest, TokenResponse, UserResponse
from app.auth.security.jwt import create_access_token
from app.auth.service.auth import authenticate_user
from app.web.dependencies import DbDep
from app.web.schemas import ApiResponse

router = APIRouter(prefix="/auth", tags=["鉴权"])


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(payload: LoginRequest, db: DbDep) -> ApiResponse[TokenResponse]:
    """邮箱 + 密码 → JWT"""
    user = await authenticate_user(db, payload.email, payload.password)
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
