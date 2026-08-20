"""任务队列 / 处理追踪域模型（3 张表）。

注意：本域表结构来自 WeKnora（DB 去重队列 + 死信 + 单层跨度树），
与旧 processing_runs/spans + Dramatiq 的取舍见 ADR-0001 与 Spec §5 后续任务。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TaskPendingOp(Base):
    """通用持久化去重任务队列（task_type+scope+scope_id 定位；claimed_at 过期可恢复）。"""

    __tablename__ = "task_pending_ops"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 任务类型（如 wiki:ingest，与 asynq 任务类型对应）
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # knowledge_base / knowledge / tenant
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 操作名
    op: Mapped[str] = mapped_column(String(32), nullable=False)
    # 去重键（空 = 不去重）
    dedup_key: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # 批内重试计数（超限进死信）
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # 认领时间（NULL=未认领；超过 stale 阈值视为崩溃可恢复）
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskDeadLetter(Base):
    """重试耗尽任务的永久归档（payload 留存，可 SQL 手动重放）。"""

    __tablename__ = "task_dead_letters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    task_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 关联 ID（wiki 摄取放 knowledge_id，便于按源文档聚类）
    related_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    # 失败时的原始任务载荷
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # 最后错误（长堆栈原文保留）
    last_error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False)
    failed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class KnowledgeProcessingSpan(TimestampMixin, Base):
    """文档处理链路追踪（跨度树：root/stage/subspan/generation）。"""

    __tablename__ = "knowledge_processing_spans"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    knowledge_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # 处理尝试次数
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    span_id: Mapped[str] = mapped_column(String(64), nullable=False)
    parent_span_id: Mapped[str | None] = mapped_column(String(64))
    # 跨度名（阶段名）
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # root / stage / subspan / generation
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    # pending/running/done/failed/skipped/cancelled
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    input: Mapped[dict | None] = mapped_column(JSONB)
    output: Mapped[dict | None] = mapped_column(JSONB)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    # 完整堆栈原文
    error_detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(BigInteger)
