"""
依赖注入模块

提供：
- get_db: 异步数据库会话 yield 依赖
- get_current_user: 当前用户依赖（JWT 解码 + DB 查询）
"""
from typing import Annotated, AsyncIterator, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_handler import decode_token
from app.config import settings
from app.database import async_session_factory
from app.models.user import User

# OAuth2 password bearer（用于 Swagger UI 的 Authorize 按钮）
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_PREFIX}/auth/login",
    auto_error=True,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """获取异步数据库会话（yield 依赖）

    自动处理事务：出错时 rollback，正常结束时由调用方决定 commit。
    """
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """从 JWT 解析当前用户（HS256）"""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        user_id_str: Optional[str] = payload.get("sub")
        if user_id_str is None:
            raise credentials_exception
        user_id = int(user_id_str)
    except (ValueError, Exception) as exc:
        raise credentials_exception from exc

    result = await db.execute(select(User).where(User.id == user_id).limit(1))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active or user.deleted_at is not None:
        raise credentials_exception
    return user


# 类型别名（简化路由签名）
DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]

