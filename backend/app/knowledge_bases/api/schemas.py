"""
KnowledgeBase 相关 schemas

包含 API 请求/响应契约（KBCreate / KBResponse）
和内部检索结果数据结构（RetrievalResult）。
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class KBCreate(BaseModel):
    """创建 KB 请求"""
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=1000)
    embedding_model: str = Field("BAAI/bge-m3", max_length=100)
    embedding_dim: int = Field(1024, ge=1, le=8192)
    vector_enabled: bool = True
    keyword_enabled: bool = True
    wiki_enabled: bool = True
    graph_enabled: bool = False


class KBResponse(BaseModel):
    """KB 响应"""
    id: int
    name: str
    description: str
    embedding_model: str
    embedding_dim: int
    vector_enabled: bool
    keyword_enabled: bool
    wiki_enabled: bool
    graph_enabled: bool
    tenant_id: int

    model_config = {"from_attributes": True}


class RetrievalResult(BaseModel):
    """单条检索结果"""
    # chunk 标识
    chunk_id: int = Field(..., description="content_chunks.id")
    document_id: int = Field(..., description="逻辑文档引用")
    revision_id: int = Field(..., description="生效文档版本引用")
    # 检索评分
    score: float = Field(..., description="融合后 RRF 分数或单路原始分数")
    match_type: str = Field(
        "rrf", description="来源标记：vector / bm25 / rrf / nearby"
    )
    # chunk 正文
    text: str = Field(..., description="chunk 原文")
    chunk_index: int = Field(..., description="文档内从 0 开始的顺序")
    # 相邻块（nearby 增强，match_type=nearby）
    context: list[RetrievalResult] = Field(
        default_factory=list, description="相邻 chunk 列表（chunk_index±1）"
    )
    # 文档元信息（供 P1 引用回链使用）
    document_title: str = Field("", description="文档标题")
    source_type: str = Field("unknown", description="来源类型")
    source_locator: dict = Field(
        default_factory=dict, description="PDF 页码/Excel sheet 等原文位置"
    )
    # 引用编号（由 P1 IntoChatMessagePlugin 分配，P0 检索阶段为空）
    citation_id: int | None = Field(
        None, description="引用编号，P1 阶段分配"
    )
