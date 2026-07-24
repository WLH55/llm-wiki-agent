"""
Search schemas
"""
from typing import Optional

from pydantic import BaseModel, Field


class ChunkHit(BaseModel):
    """单条召回结果"""
    chunk_id: int
    doc_id: str
    text: str
    score: float = Field(..., description="融合后 RRF 分数")
    rank_source: str = Field(
        "rrf", description="来源标记：vector / bm25 / rrf"
    )
    distance: Optional[float] = Field(
        None, description="向量距离（仅 vector 路径有）"
    )
    bm25_rank: Optional[float] = Field(
        None, description="BM25 相关性（仅 bm25 路径有）"
    )


class SearchResponse(BaseModel):
    """搜索响应"""
    query: str
    kb_id: int
    mode: str
    total: int
    hits: list[ChunkHit]
