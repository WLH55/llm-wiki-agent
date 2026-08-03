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

    # 内部关联 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 稳定公开 ID，全局唯一
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    # 创建者自家 tenant 逻辑引用
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 组织拥有者 user 逻辑引用
    owner_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 组织名称
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # 组织说明
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)


class OrgMember(Base):
    """组织成员关系；移除即删行，无软删除。"""

    __tablename__ = "org_members"

    # 内部关联 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 所属组织逻辑引用
    org_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 成员 user 逻辑引用
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 组织内角色：admin / editor / viewer
    role: Mapped[str] = mapped_column(String(50), default="viewer", nullable=False)
    # 加入组织时间
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 更新时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class KBShare(Base, TimestampMixin):
    """KB 到组织的共享授权（org 级，无 user_id）"""

    __tablename__ = "kb_shares"

    # 内部关联 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 被共享的 KB 逻辑引用
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 接收共享的组织逻辑引用
    org_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 共享权限：read / editor / admin
    permission: Mapped[str] = mapped_column(String(50), default="read", nullable=False)
    # 发起共享的 user 逻辑引用
    shared_by: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # 发起共享时间
    shared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class LLMProvider(Base, TimestampMixin):
    """LLM 服务商配置（admin 维护）"""

    __tablename__ = "llm_providers"

    # 内部关联 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 服务商展示名
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # API 基地址
    base_url: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    # 协议：openai / anthropic / gemini
    protocol: Mapped[str] = mapped_column(String(30), default="openai", nullable=False)
    # 默认可用模型列表
    default_models: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # 是否启用
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class UserLLMKey(Base, TimestampMixin):
    """用户 BYOK 密钥（Fernet 加密存储）"""

    __tablename__ = "user_llm_keys"

    # 内部关联 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 所属 user 逻辑引用
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 绑定的服务商逻辑引用
    provider_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 密钥密文
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    # 用户选择的 LLM 模型
    selected_llm_model: Mapped[str | None] = mapped_column(
        String(200), default=None
    )
    # 是否启用
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
