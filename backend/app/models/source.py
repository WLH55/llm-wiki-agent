"""
Source model（原始文档来源：manual / RSS / Yuque / Feishu）

按 2026-08-02 定稿 spec 重建：增 public_id / enabled / config_version /
last_synced_at；sync_cursor 由 VARCHAR 改 JSONB；类型统一 BigInteger。
全库不建外键。
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Source(Base, TimestampMixin, TenantMixin):
    """文档来源（MVP 只 manual）"""
    __tablename__ = "sources"

    # 内部关联 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # API、日志和导出使用的稳定公开 ID，全局唯一
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    # KB 逻辑引用
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 已注册的 Source Adapter 类型；MVP 为 manual
    source_type: Mapped[str] = mapped_column(
        String(50), default="manual", nullable=False
    )
    # 用户可修改的显示名称，不作为同步身份
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 是否继续接收上传或执行同步；暂停不删除已有内容
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Adapter 非敏感配置；按 source_type 对应 JSON Schema 校验
    config: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # Adapter 增量同步游标（结构化 JSON）；只有同步成功后才更新
    sync_cursor: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # Source 配置修订号
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 最近一次成功完成同步的时间
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
