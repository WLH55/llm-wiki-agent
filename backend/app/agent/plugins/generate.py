"""
GeneratePlugin：LLM 生成答案（P1 spec #10）

- chunks 为空：固定话术兜底，不调 LLM
- 流式：token 逐个拼接 context.answer + 推送 token_sink（供 SSE 输出）
- ModelKeyInvalidError：context.error = MODEL_KEY_INVALID（端点转 SSE error 事件）
- 超时等其余异常向上抛（快速失败，不吞错误）

llm_client 由组装层注入（方案 A：插件不读 DB、不建连接）。
"""
import logging

from app.agent.plugins.base import ChatContext, Plugin
from app.agent.plugins.into_chat_message import NO_RESULT_ANSWER
from app.core.exceptions import ModelKeyInvalidError

logger = logging.getLogger(__name__)


class GeneratePlugin(Plugin):
    """GENERATE：流式调用 LLM 生成答案。"""
    event = "GENERATE"

    def __init__(self, llm_client, token_sink=None):
        self._llm_client = llm_client
        # async callable：接收单个 token，供 SSE 实时推送
        self._token_sink = token_sink

    async def on_event(self, event: str, context: ChatContext) -> None:
        # 无结果兜底：不调 LLM，直接固定话术（P1 spec §4.4）
        if not context.chunks:
            context.answer = NO_RESULT_ANSWER
            return
        try:
            parts: list[str] = []
            async for token in self._llm_client.stream_chat(
                [
                    {"role": "system", "content": context.prompt},
                    {"role": "user", "content": context.query},
                ],
            ):
                parts.append(token)
                if self._token_sink is not None:
                    await self._token_sink(token)
            context.answer = "".join(parts)
        except ModelKeyInvalidError as exc:
            logger.warning("chat 模型 Key 失效: %s", exc)
            context.error = "MODEL_KEY_INVALID"
