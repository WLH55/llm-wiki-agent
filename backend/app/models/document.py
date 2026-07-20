"""
Document model（上传的文档记录，区别于 Source）

Document = 一次具体的上传（PDF / MD / Word），归属于某个 Source
ContentChunk = Document 被解析后的内容块（向量 + 全文索引）
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Document(Base, TimestampMixin, TenantMixin):
    """上传的文档记录"""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[UUID] = mapped_column(default=uuid4, nullable=False, unique=True, index=True)
    kb_id: Mapped[int] = mapped_column(nullable=False, index=True)
    source_id: Mapped[int | None] = mapped_column(default=None, index=True)

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    minio_key: Mapped[str] = mapped_column(String(500), nullable=False)

    # pending / processing / processed / failed
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    error_message: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    parser_engine: Mapped[str] = mapped_column(String(50), default="builtin", nullable=False)
    parse_error_code: Mapped[str | None] = mapped_column(String(50), default=None, nullable=True)
    parse_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
