"""
SQLAlchemy Declarative Base + 通用 Mixin

Base: 所有 model 的基类
TimestampMixin: created_at / updated_at
SoftDeleteMixin: deleted_at（软删除；无此字段的表不混入）

2026-08-20 起数据库层全量采用 WeKnora 表结构（docs/adr/0001-adopt-weknora-schema.md）：
- 主键为 VARCHAR(36) UUID（或 SERIAL/BIGSERIAL 自增），不再有 public_id 双轨
- 索引/约束以 alembic/versions/001_weknora_baseline.py 的 DDL 为唯一权威，ORM 不重复声明索引
- WeKnora DDL 中的 20 条物理外键按原样保留（仅周边表；核心表仍为逻辑引用）
"""
from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """所有 model 的基类"""
    pass


def uuid_pk() -> Mapped[str]:
    """WeKnora 风格 VARCHAR(36) UUID 主键列（应用侧默认值；DDL 侧为 gen_random_uuid()）。"""
    return mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )


def fk(target: str) -> ForeignKey:
    """便捷构造带 CASCADE 的外键（WeKnora 外键除 users.tenant_id 外均为 CASCADE）。"""
    return ForeignKey(target, ondelete="CASCADE")


class TimestampMixin:
    """created_at / updated_at（部分 WeKnora 表无 updated_at/deleted_at，按需单独声明）"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SoftDeleteMixin:
    """软删除时间（仅 WeKnora 结构中含 deleted_at 的表混入）"""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
