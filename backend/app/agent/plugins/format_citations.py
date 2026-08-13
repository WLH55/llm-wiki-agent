"""
FormatCitationsPlugin：答案引用标注 -> citations 列表（P1 spec #11）

从 answer 提取 [N] 标注，按 citation_id 查回 chunk 元数据，
组装 Citation 列表（供 SSE done 事件补发）。
"""
import re

from app.agent.api.schemas import Citation
from app.agent.plugins.base import ChatContext, Plugin

# 答案中的 [N] 标注（N 为 1 起编号）
CITATION_PATTERN = re.compile(r"\[(\d+)\]")


class FormatCitationsPlugin(Plugin):
    """FORMAT_CITATIONS：提取 [N] -> 映射 chunk -> Citation 列表。"""
    event = "FORMAT_CITATIONS"

    async def on_event(self, event: str, context: ChatContext) -> None:
        if not context.answer:
            return
        # citation_id -> chunk 映射（IntoChatMessagePlugin 已分配）
        by_id = {
            chunk.citation_id: chunk
            for chunk in context.chunks
            if chunk.citation_id is not None
        }
        citations: list[Citation] = []
        seen: set[int] = set()
        for match in CITATION_PATTERN.finditer(context.answer):
            citation_id = int(match.group(1))
            if citation_id in seen:
                continue
            seen.add(citation_id)
            chunk = by_id.get(citation_id)
            if chunk is None:
                continue
            citations.append(
                Citation(
                    id=citation_id,
                    title=chunk.document_title,
                    source=chunk.source_type,
                    chunk_id=chunk.chunk_id,
                )
            )
        context.citations = citations
