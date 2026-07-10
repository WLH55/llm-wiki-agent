"""
Source model（原始文档来源：manual / RSS / Yuque / Feishu）

参 ADR-0007：MVP 只实现 manual adapter
"""
from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Source(Base, TimestampMixin, TenantMixin):
    """文档来源（MVP 只 manual）"""
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(
        String(50), default="manual", nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    sync_cursor: Mapped[str] = mapped_column(String(500), default="", nullable=False)
