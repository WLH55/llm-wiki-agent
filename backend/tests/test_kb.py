"""
KB 测试：创建 / 列表 / 详情
"""
import pytest

from app.config import settings


@pytest.mark.asyncio
async def test_create_kb_default_config(client, auth_token):
    """创建 KB → 默认 bge-m3 + 1024 维 + 混合 IndexingStrategy"""
    response = await client.post(
        "/api/v1/kb",
        json={"name": "测试 KB"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "测试 KB"
    assert data["embedding_model"] == "BAAI/bge-m3"
    assert data["embedding_dim"] == 1024
    assert data["vector_enabled"] is True
    assert data["keyword_enabled"] is True
    assert data["wiki_enabled"] is True
    assert data["graph_enabled"] is False


@pytest.mark.asyncio
async def test_list_kbs(client, auth_token):
    """列出 KB"""
    # 先创建一个
    await client.post(
        "/api/v1/kb",
        json={"name": "KB for list"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    # 再列出
    response = await client.get(
        "/api/v1/kb",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert isinstance(data, list)
    assert any(kb["name"] == "KB for list" for kb in data)


@pytest.mark.asyncio
async def test_list_kbs_without_token_in_dev(client):
    """开发调试阶段允许不带 token 访问 KB 接口"""
    previous = settings.AUTH_ENABLED
    settings.AUTH_ENABLED = False
    try:
        response = await client.get("/api/v1/kb")
    finally:
        settings.AUTH_ENABLED = previous
    assert response.status_code == 200
    assert isinstance(response.json()["data"], list)


@pytest.mark.asyncio
async def test_get_kb_not_found(client, auth_token):
    """查询不存在的 KB → 400 ResourceNotFound"""
    response = await client.get(
        "/api/v1/kb/99999",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 400
