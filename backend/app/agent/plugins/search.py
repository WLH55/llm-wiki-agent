"""
SearchPlugin：调用 P0 检索 service 获取候选块（P1 spec #7）

retrieval.search() 已内置 embedding Key 失效降级纯 BM25（ADR-0020 联动），
插件只负责编排调用与结果写入，不额外处理降级。
"""
from app.agent.plugins.base import ChatContext, Plugin
from app.knowledge_bases.service.retrieval import search


class SearchPlugin(Plugin):
    """SEARCH：检索 chunks 写入 context。db 由组装层注入。"""
    event = "SEARCH"

    def __init__(self, db):
        self._db = db

    async def on_event(self, event: str, context: ChatContext) -> None:
        # 过检索：多取候选，后续 FILTER_TOP_K 再截断到 limit
        context.chunks = await search(
            self._db,
            kb_id=context.kb_id,
            query=context.query,
            limit=max(context.limit * 5, 50),
        )
