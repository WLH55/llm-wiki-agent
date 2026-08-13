"""
IntoChatMessagePlugin：检索结果渲染为 LLM 上下文（P1 spec #9）

- 按顺序给每条 chunk 分配 citation_id（1..N）
- XML 结构化上下文：<documents> 元信息头 + <context id="N"> 逐条正文
- 严格模式 system prompt（P1 spec §4.4）
- chunks 为空时不渲染（GeneratePlugin 会走无结果兜底）
"""
from app.agent.plugins.base import ChatContext, Plugin

# 无结果固定话术（P1 spec §4.4，GeneratePlugin 兜底复用）
NO_RESULT_ANSWER = "根据知识库中的信息，无法回答该问题。"

# 严格模式 system prompt（P1 spec §4.4 草案）
SYSTEM_PROMPT = (
    "你是一个知识库问答助手。请严格基于以下检索到的上下文回答用户问题。\n"
    "\n"
    "规则：\n"
    "1. 只使用上下文中的信息回答，禁止使用先验知识\n"
    "2. 每句断言后用 [N] 标注引用来源编号\n"
    "3. 如果上下文中没有足够信息回答问题，回答："
    f'"{NO_RESULT_ANSWER}"\n'
    "4. 不要编造、猜测或推断上下文中不存在的内容"
)


class IntoChatMessagePlugin(Plugin):
    """INTO_CHAT_MESSAGE：分配 citation_id + 渲染 XML 上下文 + 拼 prompt。"""
    event = "INTO_CHAT_MESSAGE"

    async def on_event(self, event: str, context: ChatContext) -> None:
        if not context.chunks:
            context.prompt = None
            return
        # 按顺序分配引用编号（1 起）
        for index, chunk in enumerate(context.chunks, start=1):
            chunk.citation_id = index
        context.prompt = self._build_prompt(context)

    def _build_prompt(self, context: ChatContext) -> str:
        documents = "\n".join(
            '<context id="{chunk.citation_id}">{chunk.text}</context>'.format(
                chunk=chunk,
            )
            for chunk in context.chunks
        )
        return (
            f"{SYSTEM_PROMPT}\n\n"
            "<documents>\n"
            f"{documents}\n"
            "</documents>\n\n"
            f"用户问题：{context.query}"
        )
