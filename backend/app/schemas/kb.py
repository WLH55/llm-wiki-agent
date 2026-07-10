"""
KnowledgeBase 相关 schemas
"""
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
