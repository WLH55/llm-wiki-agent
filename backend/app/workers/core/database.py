"""worker 模块私有数据库连接池。

与 API 进程的共享池（app.models.database）完全隔离：
asyncpg 连接绑定创建它的 event loop，本池只允许在 dramatiq AsyncIO
EventLoopThread 的 loop 上使用（actor + RunFailureMiddleware），禁止跨 loop 复用。
reaper 线程也不共用本池，见 reaper.py（线程内自建独立 engine）。

engine 创建是惰性的（首次查询才连接），API 进程 import 本模块不会产生连接。
"""
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

# 单 worker 进程一次只执行一条消息（--threads 1），并发极低，小池即可；
# 默认 8 进程 x 小池也避免逼近 Postgres max_connections
worker_engine = create_async_engine(
    settings.POSTGRES_DSN,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
)

# worker 私有会话工厂（actor 执行器 / RunFailureMiddleware 使用）
worker_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=worker_engine,
    expire_on_commit=False,
    autoflush=False,
)
