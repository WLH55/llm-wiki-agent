"""Agent / MCP / Web 搜索域模型（6 张表）。"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, fk, uuid_pk


class CustomAgent(TimestampMixin, SoftDeleteMixin, Base):
    """自定义 Agent（GPTs 式）；复合主键 (id, tenant_id) 允许同 id 多租户内置 Agent。"""

    __tablename__ = "custom_agents"

    # 复合主键：id 默认应用侧生成
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    avatar: Mapped[str | None] = mapped_column(String(64))
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tenant_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by: Mapped[str | None] = mapped_column(String(36))
    # Agent 配置（agent_mode、system_prompt、模型、工具、检索参数等）
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 只读成员是否可运行
    runnable_by_viewer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class McpService(TimestampMixin, SoftDeleteMixin, Base):
    """MCP 服务注册（sse/streamable-http/stdio 传输），支持认证与内置服务。"""

    __tablename__ = "mcp_services"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool | None] = mapped_column(Boolean, default=True)
    transport_type: Mapped[str] = mapped_column(String(50), nullable=False)
    url: Mapped[str | None] = mapped_column(String(512))
    headers: Mapped[dict | None] = mapped_column(JSONB)
    auth_config: Mapped[dict | None] = mapped_column(JSONB)
    advanced_config: Mapped[dict | None] = mapped_column(JSONB)
    # stdio 启动配置
    stdio_config: Mapped[dict | None] = mapped_column(JSONB)
    env_vars: Mapped[dict | None] = mapped_column(JSONB)
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class McpToolApproval(TimestampMixin, Base):
    """MCP 工具级审批开关。"""

    __tablename__ = "mcp_tool_approvals"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    service_id: Mapped[str] = mapped_column(String(36), fk("mcp_services.id"), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(512), nullable=False)
    require_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class McpOauthClient(TimestampMixin, Base):
    """MCP OAuth 客户端注册。"""

    __tablename__ = "mcp_oauth_clients"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    service_id: Mapped[str] = mapped_column(String(36), fk("mcp_services.id"), nullable=False)
    client_id: Mapped[str] = mapped_column(String(512), nullable=False)
    client_secret: Mapped[str | None] = mapped_column(Text)
    redirect_uri: Mapped[str | None] = mapped_column(String(1024))


class McpOauthToken(TimestampMixin, Base):
    """MCP OAuth 用户授权令牌（principal 身份模型 + 刷新租约防并发）。"""

    __tablename__ = "mcp_oauth_tokens"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # 平台用户 ID（兼容旧数据）
    user_id: Mapped[str] = mapped_column(String(512), nullable=False)
    service_id: Mapped[str] = mapped_column(String(36), fk("mcp_services.id"), nullable=False)
    access_token: Mapped[str | None] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    token_type: Mapped[str | None] = mapped_column(String(32))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 主体类型：web_user 等
    principal_type: Mapped[str | None] = mapped_column(String(32))
    principal_id: Mapped[str | None] = mapped_column(String(512))
    # 刷新租约（防并发刷新）
    refresh_lease_id: Mapped[str | None] = mapped_column(String(36))
    refresh_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebSearchProvider(TimestampMixin, SoftDeleteMixin, Base):
    """Web 搜索提供商配置（bing/serper/tavily 等）。"""

    __tablename__ = "web_search_providers"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    parameters: Mapped[dict | None] = mapped_column(JSONB)
    is_default: Mapped[bool | None] = mapped_column(Boolean, default=False)
