"""
Source model（原始文档来源：manual / RSS / Yuque / Feishu）

按 2026-08-02 定稿 spec 重建：增 public_id / enabled / config_version /
last_synced_at；sync_cursor 由 VARCHAR 改 JSONB；类型统一 BigInteger。
全库不建外键。
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Source(Base, TimestampMixin, TenantMixin):
    """文档来源（MVP 只 manual）"""
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(
        String(50), default="manual", nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    sync_cursor: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
