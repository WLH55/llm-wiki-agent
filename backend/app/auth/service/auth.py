"""鉴权应用服务。"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security.password import verify_password
from app.core.exceptions import BusinessValidationException
from app.models.user import User


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """校验用户凭证并返回有效用户。"""
    result = await db.execute(select(User).where(User.email == email).limit(1))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        raise BusinessValidationException("邮箱或密码错误")
    if not user.is_active or user.deleted_at is not None:
        raise BusinessValidationException("用户已禁用")
    return user
