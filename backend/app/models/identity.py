"""租户 / 用户 / 认证 / 权限域模型（8 张表）。"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, fk, uuid_pk


class Tenant(TimestampMixin, SoftDeleteMixin, Base):
    """系统多租户核心：配额、全局 Agent/检索/存储配置。"""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # 检索引擎配置列表
    retriever_engines: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str | None] = mapped_column(String(50), default="active")
    business: Mapped[str] = mapped_column(String(255), nullable=False)
    # 存储配额（字节），默认 10GB
    storage_quota: Mapped[int] = mapped_column(BigInteger, nullable=False, default=10737418240)
    storage_used: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    agent_config: Mapped[dict | None] = mapped_column(JSONB)
    context_config: Mapped[dict | None] = mapped_column(JSONB)
    conversation_config: Mapped[dict | None] = mapped_column(JSONB)
    web_search_config: Mapped[dict | None] = mapped_column(JSONB)
    # 解析引擎覆盖配置（mineru_endpoint 等），优先于环境变量
    parser_engine_config: Mapped[dict | None] = mapped_column(JSONB)
    storage_engine_config: Mapped[dict | None] = mapped_column(JSONB)
    chat_history_config: Mapped[dict | None] = mapped_column(JSONB)
    retrieval_config: Mapped[dict | None] = mapped_column(JSONB)
    # 租户级第三方凭据（应用层加密）
    credentials: Mapped[dict | None] = mapped_column(JSONB)
    api_principal_config: Mapped[dict | None] = mapped_column(JSONB)
    default_storage_backend_id: Mapped[str | None] = mapped_column(String(36))


class User(TimestampMixin, SoftDeleteMixin, Base):
    """用户账户，可跨租户（can_access_all_tenants），is_system_admin 为平台级管理员。"""

    __tablename__ = "users"

    id: Mapped[str] = uuid_pk()
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar: Mapped[str | None] = mapped_column(String(500))
    # 主租户（可空，跨租户用户）；SET NULL 与 WeKnora DDL 一致
    tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL", name="fk_users_tenant")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_access_all_tenants: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 用户偏好 JSON（记忆开关等 UI 配置）
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    is_system_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class AuthToken(TimestampMixin, Base):
    """登录令牌（access_token/refresh_token），支持撤销。"""

    __tablename__ = "auth_tokens"

    id: Mapped[str] = uuid_pk()
    user_id: Mapped[str] = mapped_column(
        String(36), fk("users.id"), nullable=False
    )
    token: Mapped[str] = mapped_column(Text, nullable=False)
    token_type: Mapped[str] = mapped_column(String(50), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class TenantMember(TimestampMixin, SoftDeleteMixin, Base):
    """租户内成员与角色（owner/admin/contributor/viewer）。"""

    __tablename__ = "tenant_members"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="contributor")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    invited_by: Mapped[str | None] = mapped_column(String(36))
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(),
    )


class TenantInvitation(TimestampMixin, SoftDeleteMixin, Base):
    """租户邀请（定向邀请 + 分享链接两种模式）。"""

    __tablename__ = "tenant_invitations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    invitee_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    invited_by: Mapped[str | None] = mapped_column(String(36))
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    message: Mapped[str | None] = mapped_column(String(500))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # 分享链接注册令牌（明文，短 TTL）
    token: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 通过该邀请完成注册的人数（分享链接累积）
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TenantApiKey(TimestampMixin, Base):
    """租户/平台级 API Key（哈希存储 + 知识库白名单 + 能力授权）。"""

    __tablename__ = "tenant_api_keys"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # scope_type=platform 时为 NULL（CHECK 约束在 DDL 侧）
    tenant_id: Mapped[int | None] = mapped_column(fk("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    # 原始 Key（应用层加密存储）
    api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    full_access: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    knowledge_base_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    capabilities: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # 作用域：tenant / platform
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False, default="tenant")


class SystemSetting(TimestampMixin, Base):
    """平台级设置（键值 JSONB），仅系统管理员可改。"""

    __tablename__ = "system_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # 值类型：int/string/bool/array/object
    value_type: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    requires_restart: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_modified_by: Mapped[str] = mapped_column(String(36), nullable=False, default="")


class AuditLog(Base):
    """操作审计（谁在何时对什么目标做了什么，含请求路径）。"""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    target_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    target_user_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    request_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    request_method: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    # success / failure
    outcome: Mapped[str] = mapped_column(String(16), nullable=False, default="success")
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(),
    )
