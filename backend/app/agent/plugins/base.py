"""
Agent Pipeline 插件体系（P1 spec：插件化事件驱动流水线）

base.py 是插件骨架（Plugin 接口 + EventManager + ChatContext）；
search.py / filter_top_k.py 等具体插件直接放在本目录（Batch 3）。

EventManager 按 PIPELINE 事件序列编排 Plugin；Plugin 之间通过 ChatContext
传递状态。新增能力（rerank/查询重写）= 新增 Plugin + 注册事件位，不改既有 Plugin。

MVP 5 事件：SEARCH -> FILTER_TOP_K -> INTO_CHAT_MESSAGE -> GENERATE -> FORMAT_CITATIONS。
QUERY_UNDERSTAND / CHUNK_RERANK / CHUNK_MERGE / LOAD_HISTORY 为预留事件位，MVP 不注册。
"""
from dataclasses import dataclass, field

from app.agent.api.schemas import Citation
from app.knowledge_bases.api.schemas import RetrievalResult


@dataclass
class ChatContext:
    """Plugin 之间传递状态的上下文。"""
    query: str
    kb_id: int
    tenant_id: int
    limit: int = 5
    chunks: list[RetrievalResult] = field(default_factory=list)
    prompt: str | None = None
    answer: str | None = None
    citations: list[Citation] = field(default_factory=list)
    error: str | None = None


class Plugin:
    """流水线插件接口：只处理自己声明的事件。"""
    event: str = ""

    async def on_event(self, event: str, context: ChatContext) -> None:
        """子类在 event 匹配时执行业务逻辑。轻量抽象方法写法。不重写就会报错"""
        raise NotImplementedError


class EventManager:
    """按 PIPELINE 事件序列编排插件。"""
    PIPELINE = [
        "SEARCH",
        "FILTER_TOP_K",
        "INTO_CHAT_MESSAGE",
        "GENERATE",
        "FORMAT_CITATIONS",
    ]

    def __init__(self, plugins: list[Plugin]):
        self._plugins = plugins

    async def run(self, context: ChatContext) -> None:
        """按事件顺序执行：对每个事件，找到声明处理它的插件并调用。"""
        for event in self.PIPELINE:
            for plugin in self._plugins:
                if plugin.event == event:
                    await plugin.on_event(event, context)
