"""
SQLAlchemy Declarative Base + 通用 Mixin

Base: 所有 model 的基类
TimestampMixin: 通用时间戳字段（created_at / updated_at / deleted_at）
TenantMixin: 租户字段（MVP 阶段所有数据都属于 bootstrap owner 的 tenant）
"""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 model 的基类"""
    pass


class TimestampMixin:
    """通用时间戳字段（软删除 via deleted_at）"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class TenantMixin:
    """租户字段（MVP 单租户，P2 多租户）"""

    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
