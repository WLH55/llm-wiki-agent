"""
文档上传 + 异步解析测试

注意：本测试依赖 worker 异步处理，需要 worker 容器在跑。
测试策略：上传后轮询状态，最多等 60s。
"""
import asyncio

import pytest


@pytest.mark.asyncio
async def test_upload_md_and_wait_processed(client, auth_token):
    """上传 MD → 轮询直到 status=processed"""
    # 先创建 KB
    kb_resp = await client.post(
        "/api/v1/kb",
        json={"name": "测试 KB for doc"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    kb_id = kb_resp.json()["data"]["id"]

    # 上传 MD
    md_content = """
# 测试文档

这是一个测试 Markdown 文档，包含中文和 English 内容。

## 章节 1
向量检索是 RAG 系统的核心组件。
BM25 是经典的关键词检索算法。

## 章节 2
RRF（Reciprocal Rank Fusion）是一种简单有效的多路召回融合方法。
""".strip().encode("utf-8")

    upload_resp = await client.post(
        f"/api/v1/kb/{kb_id}/documents",
        files={"file": ("test.md", md_content, "text/markdown")},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert upload_resp.status_code == 200
    doc_id = upload_resp.json()["data"]["doc_id"]

    # 轮询状态
    for _ in range(60):
        status_resp = await client.get(
            f"/api/v1/kb/{kb_id}/documents/{doc_id}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        status = status_resp.json()["data"]["status"]
        if status == "processed":
            return
        if status == "failed":
            pytest.fail(
                f"文档处理失败: {status_resp.json()['data']['error_message']}"
            )
        await asyncio.sleep(1)

    pytest.fail("文档处理超时（60s）")
