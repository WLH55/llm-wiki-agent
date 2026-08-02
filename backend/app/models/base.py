"""
SQLAlchemy Declarative Base + 通用 Mixin

Base: 所有 model 的基类
TimestampMixin: 通用时间戳字段（created_at / updated_at / deleted_at）
TenantMixin: 租户字段（MVP 阶段所有数据都属于 bootstrap owner 的 tenant）

注意：全库不建立数据库外键（spec 决策#2，全库范围）；关联由应用层校验。
逻辑引用列统一使用 BigInteger，与 001 重建后的 DDL 一致。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, func
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
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


class TenantMixin:
    """租户字段（MVP 单租户，P2 多租户）；类型与 DDL 保持一致使用 BigInteger。"""

    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
