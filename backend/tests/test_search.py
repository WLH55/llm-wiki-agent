"""
检索测试：中文 / 英文 / 中英混排 query 都能召回

前置条件：test_document.py 已上传过文档（chunks 入库）
"""
import pytest


@pytest.mark.asyncio
async def test_search_chinese(client, auth_token):
    """中文 query 召回"""
    # 先确保有 KB（用 test_kb 创建过的，或新建一个）
    kb_resp = await client.post(
        "/api/v1/kb",
        json={"name": "search test KB"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    kb_id = kb_resp.json()["data"]["id"]

    response = await client.get(
        f"/api/v1/kb/{kb_id}/search",
        params={"q": "向量检索", "mode": "rag", "limit": 5},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["mode"] == "rag"
    assert isinstance(data["hits"], list)


@pytest.mark.asyncio
async def test_search_english(client, auth_token):
    """英文 query 召回"""
    kb_resp = await client.post(
        "/api/v1/kb",
        json={"name": "search EN test"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    kb_id = kb_resp.json()["data"]["id"]

    response = await client.get(
        f"/api/v1/kb/{kb_id}/search",
        params={"q": "vector database", "mode": "rag", "limit": 5},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_search_wiki_mode_not_implemented(client, auth_token):
    """mode=wiki 第一批未实现 → 400"""
    kb_resp = await client.post(
        "/api/v1/kb",
        json={"name": "wiki mode test"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    kb_id = kb_resp.json()["data"]["id"]

    response = await client.get(
        f"/api/v1/kb/{kb_id}/search",
        params={"q": "test", "mode": "wiki", "limit": 5},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 400
