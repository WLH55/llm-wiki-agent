"""
KnowledgeBase model（含 IndexingStrategy 四开关）

参 ADR-0009：vector_enabled / keyword_enabled / wiki_enabled / graph_enabled
"""
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class KnowledgeBase(Base, TimestampMixin, TenantMixin):
    """知识库"""
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="", nullable=False)

    # 嵌入模型绑定（每个 KB 固定一个嵌入模型）
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)

    # IndexingStrategy 四开关
    vector_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    keyword_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    wiki_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    graph_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
