"""
KnowledgeBase model（含 IndexingStrategy 四开关）

参 ADR-0009：vector_enabled / keyword_enabled / wiki_enabled / graph_enabled
"""
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class KnowledgeBase(Base, TimestampMixin, TenantMixin):
    """知识库"""
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
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

    # RAG 与 Wiki 共用同一套切块事实，具体下游不得各自覆盖。
    chunking_strategy: Mapped[str] = mapped_column(
        String(50), default="recursive_tokens", nullable=False
    )
    chunk_size_tokens: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    chunk_overlap_tokens: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    chunking_options: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    chunking_config_version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False
    )
