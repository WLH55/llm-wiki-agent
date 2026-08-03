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

    # 内部搜索记录 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # API 和排障使用的稳定请求 ID，全局唯一
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    # 租户隔离过滤
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 被搜索的 KB
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 发起搜索的用户；Agent 或系统任务为空
    user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # rag / wiki；预留未来 fused
    search_path: Mapped[str] = mapped_column(String(20), nullable=False)
    # 应用注册的具体检索方式，如 keyword / vector / hybrid / fulltext
    search_mode: Mapped[str] = mapped_column(String(30), nullable=False)
    # 脱敏后的查询文本；租户策略禁止保存文本时为空
    query_text_redacted: Mapped[str | None] = mapped_column(Text, default=None)
    # 使用租户级密钥对规范化查询计算的 HMAC 指纹，用于安全地统计重复查询
    query_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    # 请求返回的最大结果数
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    # 过滤条件、权重和 rerank 等非敏感请求快照
    request_options: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # succeeded / failed
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # 搜索总耗时
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    # 实际返回结果数量
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # 有序命中摘要，只保存结果类型、公开 ID、排名、分数和召回通道
    result_snapshot: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    # 搜索失败时的稳定机器错误码
    error_code: Mapped[str | None] = mapped_column(String(50), default=None)
    # 搜索失败时的简短错误摘要
    error_message: Mapped[str | None] = mapped_column(String(1000), default=None)
    # 单用户反馈：1 有帮助，-1 没帮助
    feedback_value: Mapped[int | None] = mapped_column(SmallInteger, default=None)
    # 用户可选反馈说明
    feedback_comment: Mapped[str | None] = mapped_column(String(1000), default=None)
    # 最近反馈时间
    feedback_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    # 搜索发生时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 按租户或部署保留策略计算的物理清理时间
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # 用户反馈等可变字段更新时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
