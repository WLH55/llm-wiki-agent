"""与具体业务模块无关的 FastAPI 共享依赖。"""

from typing import Annotated, AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import async_session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """为当前请求提供异步数据库会话。"""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


DbDep = Annotated[AsyncSession, Depends(get_db)]
