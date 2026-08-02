"""
P2+ 才用的预留表（基础设施）

按 2026-08-02 定稿 spec 重建：organizations / org_members / kb_shares /
llm_providers / user_llm_keys 五张表按 ADR-0002/0005/0006 完整形态定稿。
WikiFolder / WikiPage 已移至 app/models/wiki.py（不再作为"预留空表"，
而是按 spec 完整字段定义）。全库不建外键。
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Organization(Base, TimestampMixin):
    """组织（共享容器）"""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)


class OrgMember(Base):
    """组织成员关系；移除即删行，无软删除。"""

    __tablename__ = "org_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    org_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), default="viewer", nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KBShare(Base, TimestampMixin):
    """KB 到组织的共享授权（org 级，无 user_id）"""

    __tablename__ = "kb_shares"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    org_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    permission: Mapped[str] = mapped_column(String(50), default="read", nullable=False)
    shared_by: Mapped[int | None] = mapped_column(BigInteger, default=None)
    shared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class LLMProvider(Base, TimestampMixin):
    """LLM 服务商配置（admin 维护）"""

    __tablename__ = "llm_providers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    protocol: Mapped[str] = mapped_column(String(30), default="openai", nullable=False)
    default_models: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class UserLLMKey(Base, TimestampMixin):
    """用户 BYOK 密钥（Fernet 加密存储）"""

    __tablename__ = "user_llm_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    provider_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    selected_llm_model: Mapped[str | None] = mapped_column(
        String(200), default=None
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
