"""组织协作 / 内容分享域模型（7 张表）。"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, fk, uuid_pk


class Organization(TimestampMixin, SoftDeleteMixin, Base):
    """跨租户协作空间（共享空间），通过邀请码/审批加入。"""

    __tablename__ = "organizations"

    id: Mapped[str] = uuid_pk()
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # 邀请码（未删除且非空时唯一）
    invite_code: Mapped[str | None] = mapped_column(String(32))
    # 加入是否需要管理员审批
    require_approval: Mapped[bool | None] = mapped_column(Boolean, default=False)
    invite_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 邀请链接有效期（天）：0=永久
    invite_code_validity_days: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=7
    )
    avatar: Mapped[str] = mapped_column(String(512), default="")
    # 是否可被搜索加入
    searchable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 成员上限（0=不限制）
    member_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    # 所有者主租户 ID（不可被移出/降级）
    owner_tenant_id: Mapped[int | None] = mapped_column(BigInteger)


class OrganizationMember(TimestampMixin, Base):
    """组织成员（用户粒度）与角色：admin/editor/viewer。"""

    __tablename__ = "organization_members"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(String(36), fk("organizations.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # 成员所属租户
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")


class OrganizationTenantMember(TimestampMixin, Base):
    """组织-租户粒度成员关系（租户而非用户作为组织成员）。"""

    __tablename__ = "organization_tenant_members"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(String(36), fk("organizations.id"), nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    # 展示用：把该租户带进组织的代表用户
    representative_user_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    joined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OrganizationJoinRequest(TimestampMixin, Base):
    """加入/升级角色的审批流（request_type: join/upgrade）。"""

    __tablename__ = "organization_join_requests"

    id: Mapped[str] = uuid_pk()
    organization_id: Mapped[str] = mapped_column(String(36), fk("organizations.id"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # pending / approved / rejected
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    # 申请角色：admin/editor/viewer
    requested_role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    # join（新成员）/ upgrade（角色升级）
    request_type: Mapped[str] = mapped_column(String(32), nullable=False, default="join")
    # 原角色（升级时）
    prev_role: Mapped[str | None] = mapped_column(String(32))
    # 申请留言
    message: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(36))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 审批意见
    review_message: Mapped[str | None] = mapped_column(Text)


class KbShare(TimestampMixin, SoftDeleteMixin, Base):
    """知识库→组织分享，跨租户访问（source_tenant_id 记录源）。"""

    __tablename__ = "kb_shares"

    id: Mapped[str] = uuid_pk()
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36), fk("knowledge_bases.id"), nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        String(36), fk("organizations.id"), nullable=False
    )
    shared_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # 知识库源租户（跨租户 Embedding 模型访问）
    source_tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # admin / editor / viewer
    permission: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")


class AgentShare(TimestampMixin, SoftDeleteMixin, Base):
    """自定义 Agent→组织分享（复合外键指向 custom_agents(id, tenant_id)）。"""

    __tablename__ = "agent_shares"

    id: Mapped[str] = uuid_pk()
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        String(36), fk("organizations.id"), nullable=False
    )
    shared_by_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # Agent 源租户（与 agent_id 组成复合外键）
    source_tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    permission: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    __table_args__ = (
        ForeignKeyConstraint(
            ["agent_id", "source_tenant_id"],
            ["custom_agents.id", "custom_agents.tenant_id"],
            ondelete="CASCADE",
        ),
    )


class TenantDisabledSharedAgent(Base):
    """租户级禁用共享 Agent 名单。"""

    __tablename__ = "tenant_disabled_shared_agents"

    tenant_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_tenant_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
