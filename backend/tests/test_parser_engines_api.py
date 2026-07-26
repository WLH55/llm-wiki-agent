"""GET /api/v1/parsers/engines 契约测试：鉴权 + 响应结构。"""

import pytest


@pytest.mark.asyncio
async def test_list_parser_engines_requires_auth(client):
    response = await client.get("/api/v1/parsers/engines")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_parser_engines_returns_engine_capabilities(client, auth_token):
    response = await client.get(
        "/api/v1/parsers/engines",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert "uploadable_file_types" in data
    assert "engines" in data
    names = {engine["name"] for engine in data["engines"]}
    assert "builtin" in names
    for engine in data["engines"]:
        assert set(engine["file_types"]) <= set(data["uploadable_file_types"])
