"""数据源同步域模型（2 张表）。"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, fk, uuid_pk


class DataSource(TimestampMixin, SoftDeleteMixin, Base):
    """外部数据源（webhook/api/database/file）定时同步到知识库。"""

    __tablename__ = "data_sources"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(36), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # webhook / api / database / file 等
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[dict | None] = mapped_column(JSONB)
    # 同步计划（cron）
    sync_schedule: Mapped[str | None] = mapped_column(String(100))
    # full / incremental
    sync_mode: Mapped[str | None] = mapped_column(String(20), default="incremental")
    # active / paused 等
    status: Mapped[str | None] = mapped_column(String(32), default="active")
    # overwrite / skip 等
    conflict_strategy: Mapped[str | None] = mapped_column(String(32), default="overwrite")
    # 是否同步删除
    sync_deletions: Mapped[bool | None] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 增量游标
    last_sync_cursor: Mapped[dict | None] = mapped_column(JSONB)
    last_sync_result: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    # 同步日志保留天数
    sync_log_retention_days: Mapped[int | None] = mapped_column(Integer, default=30)


class SyncLog(TimestampMixin, Base):
    """数据源同步执行日志与统计。"""

    __tablename__ = "sync_logs"

    id: Mapped[str] = uuid_pk()
    data_source_id: Mapped[str] = mapped_column(String(36), fk("data_sources.id"), nullable=False)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # running / success / failed
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    items_total: Mapped[int | None] = mapped_column(Integer, default=0)
    items_created: Mapped[int | None] = mapped_column(Integer, default=0)
    items_updated: Mapped[int | None] = mapped_column(Integer, default=0)
    items_deleted: Mapped[int | None] = mapped_column(Integer, default=0)
    items_skipped: Mapped[int | None] = mapped_column(Integer, default=0)
    items_failed: Mapped[int | None] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSONB)
