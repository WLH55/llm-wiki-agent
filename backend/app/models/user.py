"""
User + Tenant models

按 2026-08-02 定稿 spec 重建：tenants 增 public_id/owner_id；
users 增 is_email_verified/last_login_at。全库不建外键。
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Tenant(Base, TimestampMixin):
    """租户（自家空间）；每个用户自注册时自动创建一条。"""

    __tablename__ = "tenants"

    # 内部关联 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # API、日志和导出使用的稳定公开 ID，全局唯一
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    # 拥有者 user 逻辑引用
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 租户名称
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class User(Base, TimestampMixin):
    """用户（MVP 单 owner，P2 多用户）"""

    __tablename__ = "users"

    # 内部关联 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 自家 tenant 逻辑引用
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 登录邮箱，全局唯一
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # 密码哈希（argon2id）
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # 租户内角色：owner / admin / contributor / viewer
    role: Mapped[str] = mapped_column(String(50), default="owner", nullable=False)
    # 是否启用；停用后禁止登录
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 邮箱是否已验证
    is_email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # 最近一次登录时间
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
