"""
Pytest 全局 fixtures

测试前置条件：
1. docker-compose up（postgres + redis + minio 已起）
2. alembic upgrade head（schema 已迁移）
3. ensure_bootstrap_owner 已跑（启动 backend 时自动跑）

测试 fixture：
- db_session: 异步 db 会话
- client: ASGI test client（httpx）
- auth_token: 登录拿到的 JWT
"""
import asyncio
import os
from typing import AsyncIterator

# 在导入 app 模块前提供可解析的默认 DSN，避免 collection 阶段 URL 解析失败。
# 真实集成测试仍应通过环境变量/compose 指向可用 Postgres。
os.environ.setdefault(
    "POSTGRES_DSN",
    "postgresql+asyncpg://llmwiki:llmwiki@localhost:5432/llmwiki",
)
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("AUTH_ENABLED", "true")
os.environ.setdefault("BOOTSTRAP_OWNER_EMAIL", "owner@local")
os.environ.setdefault("BOOTSTRAP_OWNER_PASSWORD", "change-me")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="session")
def event_loop():
    """session 级 event loop"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator:
    """异步 db session"""
    from app.models.database import async_session_factory

    async with async_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """ASGI test client"""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_token(client: AsyncClient) -> str:
    """登录 bootstrap owner 拿 JWT"""
    email = os.getenv("BOOTSTRAP_OWNER_EMAIL", "owner@local")
    pwd = os.getenv("BOOTSTRAP_OWNER_PASSWORD", "change-me")
    response = await client.post(
        "/api/auth/login",
        json={"email": email, "password": pwd},
    )
    assert response.status_code == 200, f"登录失败: {response.text}"
    data = response.json()["data"]
    return data["access_token"]
