"""会话 / 消息 / 问答域模型（4 张表）。"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, fk, uuid_pk


class Session(TimestampMixin, SoftDeleteMixin, Base):
    """问答会话：绑定知识库与 Agent，携带检索参数（阈值、top_k）与兜底策略。"""

    __tablename__ = "sessions"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    knowledge_base_id: Mapped[str | None] = mapped_column(String(36))
    # 最大历史轮数
    max_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    # 是否启用问题改写
    enable_rewrite: Mapped[bool] = mapped_column(nullable=False, default=True)
    # fixed / model
    fallback_strategy: Mapped[str] = mapped_column(String(255), nullable=False, default="fixed")
    fallback_response: Mapped[str] = mapped_column(
        Text, nullable=False, default="很抱歉，我暂时无法回答这个问题。"
    )
    keyword_threshold: Mapped[float] = mapped_column(nullable=False, default=0.5)
    vector_threshold: Mapped[float] = mapped_column(nullable=False, default=0.5)
    rerank_model_id: Mapped[str | None] = mapped_column(String(64))
    embedding_top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    rerank_top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    rerank_threshold: Mapped[float] = mapped_column(nullable=False, default=0.65)
    summary_model_id: Mapped[str | None] = mapped_column(String(64))
    summary_parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    agent_config: Mapped[dict | None] = mapped_column(JSONB)
    # LLM 上下文管理配置（与消息存储分离）
    context_config: Mapped[dict | None] = mapped_column(JSONB)
    # 使用的 Agent ID（custom_agents.id）
    agent_id: Mapped[str | None] = mapped_column(String(36))
    user_id: Mapped[str | None] = mapped_column(String(512))
    is_pinned: Mapped[bool] = mapped_column(nullable=False, default=False)
    pinned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(TimestampMixin, SoftDeleteMixin, Base):
    """会话消息：含知识引用、Agent 步骤、渲染内容、附件等。"""

    __tablename__ = "messages"

    id: Mapped[str] = uuid_pk()
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # user / assistant / system
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 引用的知识块引用列表
    knowledge_references: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Agent 执行步骤（推理过程与工具调用）
    agent_steps: Mapped[dict | None] = mapped_column(JSONB)
    is_completed: Mapped[bool] = mapped_column(nullable=False, default=False)
    # @提及的知识库与文件（id、name、type）
    mentioned_items: Mapped[list | None] = mapped_column(JSONB, default=list)
    # 是否走兜底回复
    is_fallback: Mapped[bool | None] = mapped_column(default=False)
    # Agent 执行耗时（毫秒）
    agent_duration_ms: Mapped[int | None] = mapped_column(BigInteger, default=0)
    # 关联的知识条目 ID（聊天历史入库）
    knowledge_id: Mapped[str | None] = mapped_column(String(36))
    images: Mapped[list | None] = mapped_column(JSONB, default=list)
    # 来源渠道：web/api/im 等
    channel: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    # 完整 RAG 增强后的用户消息（跨轮保留检索上下文）
    rendered_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    attachments: Mapped[list | None] = mapped_column(JSONB, default=list)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    agent_tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    execution_context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class MessageSuggestionSet(TimestampMixin, Base):
    """助手消息的推荐问题缓存（去重键 config_hash+placement+locale）。"""

    __tablename__ = "message_suggestion_sets"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(Integer, fk("tenants.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    assistant_message_id: Mapped[str] = mapped_column(String(36), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    agent_tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 插入位置
    placement: Mapped[str] = mapped_column(String(32), nullable=False)
    # 生成配置哈希（缓存键）
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    allow_regenerate: Mapped[bool] = mapped_column(nullable=False, default=False)
    # 抑制原因（不生成时）
    suppression_reason: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    model_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 租约到期（去重）
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MessageSuggestionEvent(Base):
    """推荐问题点击/展示埋点事件。"""

    __tablename__ = "message_suggestion_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(Integer, fk("tenants.id"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    suggestion_set_id: Mapped[str] = mapped_column(
        String(36), fk("message_suggestion_sets.id"), nullable=False
    )
    question_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # shown / clicked 等
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
