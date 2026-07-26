"""
嵌入服务：兼容 OpenAI Embeddings 协议的供应商。

当前默认对接 Jina Embeddings：
- base_url: https://api.jina.ai/v1
- model: jina-embeddings-v5-text-small
- dim: 1024
"""

import logging
from typing import List, Optional

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    """获取 OpenAI 兼容 client（懒加载单例）。"""
    global _client
    if _client is None:
        if not settings.EMBEDDING_API_KEY:
            logger.warning("EMBEDDING_API_KEY 未配置，调用嵌入 API 会失败")
        _client = OpenAI(
            api_key=settings.EMBEDDING_API_KEY or "missing",
            base_url=settings.EMBEDDING_API_BASE,
        )
    return _client


def embed_texts(
    texts: List[str],
    *,
    task: str | None = "retrieval.passage",
) -> List[List[float]]:
    """批量嵌入文本，返回向量列表。

    task:
    - 入库/文档侧默认 retrieval.passage
    - 检索 query 侧使用 retrieval.query
    """
    if not texts:
        return []
    client = get_client()
    create_kwargs: dict = {
        "model": settings.EMBEDDING_MODEL,
        "input": texts,
    }
    # Jina 等供应商的扩展字段走 extra_body，保持 OpenAI SDK 兼容
    extra_body: dict = {"normalized": True}
    if task:
        extra_body["task"] = task
    create_kwargs["extra_body"] = extra_body
    response = client.embeddings.create(**create_kwargs)
    return [item.embedding for item in response.data]


def embed_one(text: str, *, task: str | None = "retrieval.query") -> List[float]:
    """便捷方法：嵌入单条文本（检索默认 query task）。"""
    return embed_texts([text], task=task)[0]
