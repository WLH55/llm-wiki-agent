"""任务运行账本与阶段记录模型。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProcessingRun(Base):
    """一次可独立调度、可审计的业务处理运行。"""

    __tablename__ = "processing_runs"

    # 内部运行 ID
    id: Mapped[int] = mapped_column(primary_key=True)
    # API、日志和排障使用的稳定公开 ID，全局唯一
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    # 租户隔离过滤
    tenant_id: Mapped[int] = mapped_column(nullable=False)
    # 运行所属 KB
    kb_id: Mapped[int] = mapped_column(nullable=False)
    # 应用注册的流程类型：source_sync / document_process / rag_index / wiki_generate
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 处理目标类型：source / revision / knowledge_base / wiki_page
    scope_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # 由 scope_type 解释的处理目标逻辑 ID
    scope_id: Mapped[int] = mapped_column(nullable=False)
    # 上级编排运行；rag_index / wiki_generate 通常指向产生候选共享 chunk set 的 document_process Run
    parent_run_id: Mapped[int | None] = mapped_column(default=None)
    # 终态后发起业务重跑时指向上一 Run；自动重试不使用
    retry_of_run_id: Mapped[int | None] = mapped_column(default=None)
    # 同一业务重跑链中的 Run 序号；自动重试不递增
    attempt_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # manual / on_ingest / schedule / retry
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # pending / running / succeeded / failed / cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # 防止 API 重试或重复消息为同一请求创建多次运行
    idempotency_key: Mapped[str | None] = mapped_column(String(255), default=None)
    # 本次实际使用的 Source/KB/RAG/Wiki 配置版本，由 run_type 解释
    effective_config_version: Mapped[int | None] = mapped_column(default=None)
    # 共享分块策略、Wiki Map 批次预算、输出语言、Prompt profile 等实际生效的非敏感运行选项快照
    options_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # 手动触发者；系统任务为空
    requested_by_user_id: Mapped[int | None] = mapped_column(default=None)
    # Run 进入失败终态时的稳定机器错误码；自动重试中的错误归 Span
    error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    # Run 进入失败终态时的简短错误摘要，不保存完整日志或堆栈
    error_message: Mapped[str | None] = mapped_column(String(1000), default=None)

    # 本 Run 第一次被 Worker 实际执行的时间，自动重试不覆盖
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    # 成功、失败或取消的结束时间
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    # 运行创建并进入等待队列的时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 状态或错误摘要的最近更新时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProcessingSpan(Base):
    """Processing Run 内可观测的阶段或单次 Worker 执行尝试。"""

    __tablename__ = "processing_spans"

    # 内部阶段 ID
    id: Mapped[int] = mapped_column(primary_key=True)
    # API 和日志追踪使用的稳定阶段 ID，全局唯一
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    # 租户隔离过滤
    tenant_id: Mapped[int] = mapped_column(nullable=False)
    # 阶段所属 KB
    kb_id: Mapped[int] = mapped_column(nullable=False)
    # 所属 processing_runs 逻辑引用
    run_id: Mapped[int] = mapped_column(nullable=False)
    # 上级阶段逻辑引用，用于表达嵌套阶段树
    parent_span_id: Mapped[int | None] = mapped_column(default=None)
    # 应用注册的阶段名称，如 parse / segment / extract_entities / embed
    span_name: Mapped[str] = mapped_column(String(50), nullable=False)
    # 同一 Run 内同一阶段的尝试序号；与 run_id + span_name 构成唯一键，对齐 WeKnora
    attempt_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # pending / running / succeeded / failed / skipped / cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # 该阶段实际使用的模型；非模型阶段为空
    model_key: Mapped[str | None] = mapped_column(String(200), default=None)
    # 模型阶段输入 token 数
    input_tokens: Mapped[int | None] = mapped_column(default=None)
    # 模型阶段输出 token 数
    output_tokens: Mapped[int | None] = mapped_column(default=None)
    # 输入/输出项数、缓存命中、重试次数等阶段专属数值指标
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # 稳定机器错误码
    error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    # 简短错误摘要，不保存完整堆栈
    error_message: Mapped[str | None] = mapped_column(String(1000), default=None)
    # 阶段实际开始时间；尚未开始便跳过或取消时为空
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    # 阶段结束时间
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    # 记录创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 状态、指标或错误摘要更新时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
