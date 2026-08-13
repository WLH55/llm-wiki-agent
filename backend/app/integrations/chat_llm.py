"""
OpenAI 兼容 chat LLM 客户端（外部系统适配器，与 embedding.py 对称）

- 端点：{base_url}/v1/chat/completions（base_url 如 https://api.deepseek.com）
- SSE 流式：逐行解析 data: 事件，yield delta content
- 超时重试：ConnectTimeout/ReadTimeout/TimeoutException 最多 3 次尝试
- 401：立即抛 ModelKeyInvalidError，不重试（Key 失效重试无意义）
"""
import json
import logging
from collections.abc import AsyncIterator

import httpx

from app.core.exceptions import LLMTimeoutError, ModelKeyInvalidError

logger = logging.getLogger(__name__)

# 单次请求最大尝试次数（P1 spec Q11：超时重试 3 次）
MAX_ATTEMPTS = 3


class LLMClient:
    """OpenAI 兼容 chat completions 客户端。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 60.0,
        http_client: httpx.AsyncClient | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        # 测试可注入 MockTransport 客户端；生产默认创建（进程生命周期内复用）
        self._client = http_client or httpx.AsyncClient()

    def _build_request(self, messages: list[dict], temperature: float) -> httpx.Request:
        return self._client.build_request(
            "POST",
            f"{self._base_url}/v1/chat/completions",
            json={
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
                "stream": True,
            },
            headers={"Authorization": f"Bearer {self._api_key}"},
            timeout=self._timeout_seconds,
        )

    async def stream_chat(
        self,
        messages: list[dict],
        temperature: float = 0.3,
    ) -> AsyncIterator[str]:
        """流式对话：yield 每个 delta 文本片段。"""
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                async for token in self._stream_once(messages, temperature):
                    yield token
                return
            except httpx.TimeoutException as exc:
                # ConnectTimeout / ReadTimeout 统一按超时重试处理
                if attempt == MAX_ATTEMPTS:
                    raise LLMTimeoutError(
                        f"chat 模型请求超时（{MAX_ATTEMPTS} 次尝试后仍失败）"
                    ) from exc
                logger.warning("chat 请求超时（第 %s/%s 次），重试中", attempt, MAX_ATTEMPTS)

    async def _stream_once(
        self,
        messages: list[dict],
        temperature: float,
    ) -> AsyncIterator[str]:
        request = self._build_request(messages, temperature)
        response = await self._client.send(request, stream=True)
        if response.status_code == 401:
            await response.aclose()
            raise ModelKeyInvalidError("对话模型 Key 失效（HTTP 401）")
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[len("data:"):].strip()
            if payload == "[DONE]":
                break
            data = json.loads(payload)
            delta = data.get("choices", [{}])[0].get("delta", {}).get("content")
            if delta:
                yield delta
        await response.aclose()
