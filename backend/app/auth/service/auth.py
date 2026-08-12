"""鉴权应用服务。业务编排层：通过 UserRepository 访问数据。"""
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.repository.user_repo import UserRepository
from app.auth.security.password import verify_password
from app.core.exceptions import BusinessValidationException
from app.models.user import User


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    """校验用户凭证并返回有效用户。"""
    repo = UserRepository(db)
    user = await repo.get_by_email(email)
    if user is None or not verify_password(password, user.password_hash):
        raise BusinessValidationException("邮箱或密码错误")
    if not user.is_active or user.deleted_at is not None:
        raise BusinessValidationException("用户已禁用")
    return user