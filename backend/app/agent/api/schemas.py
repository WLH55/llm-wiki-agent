"""
agent 模块数据契约（P1 spec §4.2）

RetrievalResult 复用 knowledge_bases（app/knowledge_bases/api/schemas.py），不在此重复定义。
"""
from pydantic import BaseModel


class Citation(BaseModel):
    """引用回链：对应答案中的 [N] 标注。"""
    id: int
    title: str
    source: str
    chunk_id: int


class ChatRequest(BaseModel):
    """POST /api/v1/kb/{kb_id}/chat 请求体。"""
    query: str
    limit: int = 5
