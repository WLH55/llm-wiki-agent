"""
鉴权测试：密码哈希 / JWT / login API
"""
import pytest

from app.auth.jwt_handler import create_access_token, decode_token
from app.auth.password import hash_password, verify_password


def test_password_hash_and_verify():
    """密码哈希 + 校验"""
    raw = "test-password-123"
    hashed = hash_password(raw)
    assert hashed != raw
    assert verify_password(raw, hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_create_and_decode():
    """JWT 创建 + 解码"""
    user_id = 42
    token = create_access_token(user_id)
    payload = decode_token(token)
    assert payload["sub"] == str(user_id)


@pytest.mark.asyncio
async def test_login_success(client):
    """登录成功（bootstrap owner 已存在）"""
    response = await client.post(
        "/api/auth/login",
        json={"email": "owner@local", "password": "change-me"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert "access_token" in body["data"]


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    """密码错误 → 400"""
    response = await client.post(
        "/api/auth/login",
        json={"email": "owner@local", "password": "wrong"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_me_with_token(client, auth_token):
    """带 JWT 调 /api/auth/me 返回当前用户"""
    response = await client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == "owner@local"
    assert data["role"] == "owner"
