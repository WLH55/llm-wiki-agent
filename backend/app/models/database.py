"""
数据库连接模块

提供异步 SQLAlchemy engine + session factory。

注意：POSTGRES_DSN 在阶段 1A 可能为空（未配置 .env），
SQLAlchemy create_async_engine 不会立即连接，仅在第一次查询时才连接。
所以空 DSN 启动不会失败，只有真正查询时才会报错。
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# 异步引擎（pool_pre_ping 避免长连接断开）
async_engine = create_async_engine(
    settings.POSTGRES_DSN,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# 异步会话工厂
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    autoflush=False,
)
