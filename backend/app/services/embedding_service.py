"""
嵌入服务：调用 SiliconFlow bge-m3 API

用 openai SDK，base_url 覆盖到 SiliconFlow。
兼容 OpenAI 协议，bge-m3 输出 1024 维。
"""
import logging
from typing import List, Optional

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    """获取 OpenAI client（懒加载单例）"""
    global _client
    if _client is None:
        if not settings.EMBEDDING_API_KEY:
            logger.warning("EMBEDDING_API_KEY 未配置，调用嵌入 API 会失败")
        _client = OpenAI(
            api_key=settings.EMBEDDING_API_KEY or "missing",
            base_url=settings.EMBEDDING_API_BASE,
        )
    return _client


def embed_texts(texts: List[str]) -> List[List[float]]:
    """批量嵌入文本，返回向量列表（1024 维 / bge-m3）"""
    if not texts:
        return []

    client = get_client()
    response = client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=texts,
    )
    return [item.embedding for item in response.data]


def embed_one(text: str) -> List[float]:
    """便捷方法：嵌入单条文本"""
    return embed_texts([text])[0]
