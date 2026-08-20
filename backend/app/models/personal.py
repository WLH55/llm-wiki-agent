"""用户个性化域模型（2 张表）。"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserResourceFavorite(Base):
    """用户收藏（资源类型：kb/agent）。"""

    __tablename__ = "user_resource_favorites"

    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # kb / agent
    resource_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    resource_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class UserKbPin(Base):
    """用户级知识库置顶。"""

    __tablename__ = "user_kb_pins"

    tenant_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kb_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    pinned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
