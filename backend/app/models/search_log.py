"""
search_logs model

按 2026-08-02 定稿 spec：检索查询、命中摘要、反馈和隐私保留策略。
不保存原始查询和完整命中正文；到达 expires_at 物理删除。全库不建外键。
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SearchLog(Base):
    """一次搜索请求的脱敏记录与单用户反馈。"""

    __tablename__ = "search_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    search_path: Mapped[str] = mapped_column(String(20), nullable=False)
    search_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    query_text_redacted: Mapped[str | None] = mapped_column(Text, default=None)
    query_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    request_options: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    result_snapshot: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    error_message: Mapped[str | None] = mapped_column(String(1000), default=None)
    feedback_value: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    feedback_comment: Mapped[str | None] = mapped_column(String(1000), default=None)
    feedback_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
