"""
KnowledgeBase model

按 2026-08-02 定稿 spec 重建：删除 embedding_model / embedding_dim /
vector_enabled / keyword_enabled / wiki_enabled / graph_enabled（这些归属
kb_rag_configs / kb_wiki_configs，见 spec 决策#3）；description 改 TEXT。
本表只保留身份、归属、通用描述和唯一的共享分块策略。
"""
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class KnowledgeBase(Base, TimestampMixin, TenantMixin):
    """知识库（RAG/Wiki 共享聚合根）"""
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)

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
