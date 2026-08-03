"""
Document + DocumentRevision models

按 2026-08-02 定稿 spec 重建：
- documents 删除 doc_id / original_filename / minio_key / status / error_message /
  parser_engine / parse_error_code / parse_metadata / processed_at（文件与处理信息
  归属 document_revisions，见 spec 决策）；source_id 改 NOT NULL。
- document_revisions 与 spec 对齐（无变化，已符合）。
全库不建外键。
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Document(Base, TimestampMixin, TenantMixin):
    """来源文档在 KB 中的稳定身份"""

    __tablename__ = "documents"

    # 内部关联 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # API 对外文档 ID，全局唯一
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True, index=True
    )
    # KB 逻辑引用
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # Source 逻辑引用
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)

    # 来源系统中的稳定文档标识；手动上传时生成，不使用文件名充当身份
    source_document_key: Mapped[str] = mapped_column(String(512), nullable=False)
    # 当前展示标题
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    # 当前已通过激活门槛、正式供 RAG/Wiki 使用的版本；首次激活成功前为空
    active_revision_id: Mapped[int | None] = mapped_column(
        BigInteger, default=None, index=True
    )
    # 修改文档元数据时的乐观锁
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class DocumentRevision(Base):
    """一次上传或同步形成的不可变原文件版本。"""

    __tablename__ = "document_revisions"

    # 内部版本 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Document 逻辑引用
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 文档内单调递增版本号
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # 来源系统提供的 revision ID、ETag 等幂等标识
    source_version: Mapped[str | None] = mapped_column(String(255), default=None)
    # 来源系统声明的修改时间
    source_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    # 本版本收到的原始文件名
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    # MIME 类型
    media_type: Mapped[str] = mapped_column(String(255), nullable=False)
    # 原文件字节数
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 原文件内容指纹
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    # 对象存储中的不可变 key
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False, unique=True)
    # 本版本选择的解析引擎
    parser_engine: Mapped[str] = mapped_column(
        String(50), default="builtin", nullable=False
    )
    # pending / processing / ready / failed
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # parser metadata、warnings 与持久化图片清单，禁止 base64
    parse_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # 手动上传者；自动同步时为空
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # 版本创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 状态或解析元数据更新时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 软删除时间
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
