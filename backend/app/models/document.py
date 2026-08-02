"""
Document + DocumentRevision models

按 2026-08-02 定稿 spec 重建：
- documents 删除 doc_id / original_filename / minio_key / status / error_message /
  parser_engine / parse_error_code / parse_metadata / processed_at（文件与处理信息
  归属 document_revisions，见 spec 决策）；source_id 改 NOT NULL。
- document_revisions 与 spec 对齐（无变化，已符合）。
全库不建外键。
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Document(Base, TimestampMixin, TenantMixin):
    """来源文档在 KB 中的稳定身份"""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True, index=True
    )
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    source_document_key: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    active_revision_id: Mapped[int | None] = mapped_column(
        BigInteger, default=None, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


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
