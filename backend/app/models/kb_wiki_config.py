"""
kb_wiki_configs model

按 2026-08-02 定稿 spec：Wiki 路径启停和页面生成配置；一个 KB 最多一条。
全库不建外键。
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class KnowledgeBaseWikiConfig(Base):
    """一个知识库最多一条 Wiki 生成配置。"""

    __tablename__ = "kb_wiki_configs"

    kb_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    generation_mode: Mapped[str] = mapped_column(
        String(20), default="manual", nullable=False
    )
    generation_model_key: Mapped[str | None] = mapped_column(String(200), default=None)
    generation_options: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
