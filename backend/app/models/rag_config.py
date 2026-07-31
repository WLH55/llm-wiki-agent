"""RAG 路径独立配置，不与共享分块或 Wiki 配置混放。"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KnowledgeBaseRagConfig(Base):
    """一个知识库最多一条 RAG 检索与 embedding 配置。"""

    __tablename__ = "kb_rag_configs"

    kb_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    vector_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    keyword_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    embedding_model_key: Mapped[str | None] = mapped_column(String(200), default=None)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, default=None)
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
