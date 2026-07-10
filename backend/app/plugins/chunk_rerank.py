"""
CHUNK_RERANK plugin 接口声明

第一批只声明接口，不实现 boost。第二批 wiki 抽取后才需要 wiki chunk boost 1.3。

参 ADR-0009 §路径 B
"""
import logging
from typing import List, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# wiki chunk boost 系数（参 ADR-0009，第二批启用）
WIKI_CHUNK_BOOST = 1.3


@runtime_checkable
class ChunkRerankPlugin(Protocol):
    """CHUNK_RERANK plugin 协议"""

    def rerank(self, chunks: List[dict], query: str) -> List[dict]:
        """对召回的 chunks 重排序"""
        ...


class DefaultChunkRerankPlugin:
    """默认实现：第一批不做 boost，原样返回"""

    def rerank(self, chunks: List[dict], query: str) -> List[dict]:
        # TODO 第二批：wiki_page chunk 分数 * WIKI_CHUNK_BOOST
        return chunks


_active_plugin: ChunkRerankPlugin = DefaultChunkRerankPlugin()


def get_chunk_rerank_plugin() -> ChunkRerankPlugin:
    """获取当前激活的 rerank plugin"""
    return _active_plugin


def set_chunk_rerank_plugin(plugin: ChunkRerankPlugin) -> None:
    """设置 rerank plugin（用于测试或扩展）"""
    global _active_plugin
    _active_plugin = plugin
