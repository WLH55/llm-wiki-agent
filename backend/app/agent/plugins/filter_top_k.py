"""
FilterTopKPlugin：截断检索结果到用户要求的 limit（P1 spec #8）
"""
from app.agent.plugins.base import ChatContext, Plugin


class FilterTopKPlugin(Plugin):
    """FILTER_TOP_K：chunks 截断到 context.limit。"""
    event = "FILTER_TOP_K"

    async def on_event(self, event: str, context: ChatContext) -> None:
        context.chunks = context.chunks[: context.limit]
