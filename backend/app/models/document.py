"""
Document model（上传的文档记录，区别于 Source）

Document = 一次具体的上传（PDF / MD / Word），归属于某个 Source
ContentChunk = Document 被解析后的内容块（向量 + 全文索引）
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Document(Base, TimestampMixin, TenantMixin):
    """上传的文档记录"""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True, index=True
    )
    doc_id: Mapped[UUID] = mapped_column(default=uuid4, nullable=False, unique=True, index=True)
    kb_id: Mapped[int] = mapped_column(nullable=False, index=True)
    source_id: Mapped[int | None] = mapped_column(default=None, index=True)

    source_document_key: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    active_revision_id: Mapped[int | None] = mapped_column(BigInteger, default=None, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    minio_key: Mapped[str] = mapped_column(String(500), nullable=False)

    # pending / processing / processed / failed
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    error_message: Mapped[str] = mapped_column(String(1000), default="", nullable=False)
    parser_engine: Mapped[str] = mapped_column(String(50), default="builtin", nullable=False)
    parse_error_code: Mapped[str | None] = mapped_column(String(50), default=None, nullable=True)
    parse_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class DocumentRevision(Base):
    """一次上传或同步形成的不可变原文件版本。"""

    __tablename__ = "document_revisions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    source_version: Mapped[str | None] = mapped_column(String(255), default=None)
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    parser_engine: Mapped[str] = mapped_column(
        String(50), default="builtin", nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    parse_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
