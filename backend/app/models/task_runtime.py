"""任务运行账本、阶段记录与可靠投递 Outbox 模型。"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProcessingRun(Base):
    """一次可独立调度、可审计的业务处理运行。"""

    __tablename__ = "processing_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    tenant_id: Mapped[int] = mapped_column(nullable=False)
    kb_id: Mapped[int] = mapped_column(nullable=False)
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(30), nullable=False)
    scope_id: Mapped[int] = mapped_column(nullable=False)
    parent_run_id: Mapped[int | None] = mapped_column(default=None)
    retry_of_run_id: Mapped[int | None] = mapped_column(default=None)
    attempt_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), default=None)
    effective_config_version: Mapped[int | None] = mapped_column(default=None)
    options_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    requested_by_user_id: Mapped[int | None] = mapped_column(default=None)
    error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    error_message: Mapped[str | None] = mapped_column(String(1000), default=None)

    # 执行租约只表达当前执行权；业务状态和进度仍由 Run/Span 保存。
    execution_token: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), default=None
    )
    execution_epoch: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    worker_id: Mapped[str | None] = mapped_column(String(255), default=None)

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProcessingSpan(Base):
    """Processing Run 内可观测的阶段或单次 Worker 执行尝试。"""

    __tablename__ = "processing_spans"

    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    tenant_id: Mapped[int] = mapped_column(nullable=False)
    kb_id: Mapped[int] = mapped_column(nullable=False)
    run_id: Mapped[int] = mapped_column(nullable=False)
    parent_span_id: Mapped[int | None] = mapped_column(default=None)
    span_name: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    model_key: Mapped[str | None] = mapped_column(String(200), default=None)
    input_tokens: Mapped[int | None] = mapped_column(default=None)
    output_tokens: Mapped[int | None] = mapped_column(default=None)
    metrics: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    error_message: Mapped[str | None] = mapped_column(String(1000), default=None)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TaskOutbox(Base):
    """等待投递到 Broker 的持久化通知，不保存业务结果。"""

    __tablename__ = "task_outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(nullable=False)
    task_name: Mapped[str] = mapped_column(String(100), nullable=False)
    queue_name: Mapped[str] = mapped_column(String(50), nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    publish_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    lock_token: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), default=None
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
