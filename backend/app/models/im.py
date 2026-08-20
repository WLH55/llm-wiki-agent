"""IM 接入 / 嵌入渠道域模型（3 张表）。"""

from sqlalchemy import BigInteger, Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, fk, uuid_pk


class ImChannel(TimestampMixin, SoftDeleteMixin, Base):
    """IM 渠道配置（企微/钉钉/飞书等：凭据、绑定 Agent/KB）。"""

    __tablename__ = "im_channels"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # wecom / dingtalk / feishu / lark 等
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # websocket / webhook
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="websocket")
    # stream（实时）/ reply（整段回复）
    output_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="stream")
    # 平台凭据（corp_id/app_secret/token 等，按平台不同）
    credentials: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 绑定知识库 ID（默认）
    knowledge_base_id: Mapped[str | None] = mapped_column(String(36), default="")
    # 机器人身份标识（防重复绑定，如 wecom:ws:{bot_id}）
    bot_identity: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # user（按用户+会话）/ thread（按线程）
    session_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="user")


class ImChannelSession(TimestampMixin, SoftDeleteMixin, Base):
    """IM 平台会话与内部 session 的映射（thread 模式支持群聊线程）。"""

    __tablename__ = "im_channel_sessions"

    id: Mapped[str] = uuid_pk()
    platform: Mapped[str] = mapped_column(String(20), nullable=False)
    # 平台用户 ID
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # 平台会话/群 ID（单聊为空）
    chat_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    session_id: Mapped[str] = mapped_column(String(36), fk("sessions.id"), nullable=False)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 渠道绑定的 Agent（空 = 默认）
    agent_id: Mapped[str | None] = mapped_column(String(36), default="")
    # active / inactive
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # 平台侧附加数据
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, default=dict)
    im_channel_id: Mapped[str | None] = mapped_column(String(36), default="")
    # 平台线程 ID（thread 模式；user 模式为空）
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")


class EmbedChannel(TimestampMixin, SoftDeleteMixin, Base):
    """公开嵌入渠道（iframe 挂件：发布令牌、CORS 白名单、限流、主题）。"""

    __tablename__ = "embed_channels"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, default="builtin-quick-answer")
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 发布令牌（网页身份验证，可轮换）
    publish_token: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 允许的跨域来源（空 = 全拒）
    allowed_origins: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    welcome_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 每 IP 每分钟请求上限
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    # 渠道级每日总请求上限
    rate_limit_per_day: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    # 主题色（如 #0052d9）
    primary_color: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    page_title: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # channel（固定标题）/ session（首条消息后自动生成）
    header_title_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="channel")
    show_suggested_questions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # bottom-right / bottom-left / top-right / top-left
    widget_position: Mapped[str] = mapped_column(String(32), nullable=False, default="bottom-right")
    allow_web_search: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_memory: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_file_upload: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 默认访客语言（zh-CN/en-US 等，空 = 跟随浏览器）
    default_locale: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    webhook_url: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    webhook_secret: Mapped[str] = mapped_column(String(128), nullable=False, default="")
