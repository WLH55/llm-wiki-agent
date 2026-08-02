"""
Wiki 表 ORM 模型

按 2026-08-02 定稿 spec 定义五张 Wiki 表：
- wiki_folders：目录树（单层父子关系，不缓存路径/深度）
- wiki_pages：页面正文、类型、slug、编辑版本
- wiki_page_links：由页面正文 [[slug|显示文字]] 同步派生的有向边
- wiki_page_document_refs：页面到具体不可变 Revision 的文档级血缘
- wiki_page_evidence_refs：页面到具体 Revision 原文片段的证据级血缘

全库不建外键；关联校验由应用层负责。
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class WikiFolder(Base, TimestampMixin, TenantMixin):
    """Wiki 目录树；slug 创建后不可修改。"""

    __tablename__ = "wiki_folders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(BigInteger, default=None, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    updated_by_user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)


class WikiPage(Base, TimestampMixin, TenantMixin):
    """Wiki 页面；slug 创建后不可修改，改名只改 title/aliases。"""

    __tablename__ = "wiki_pages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    page_type: Mapped[str] = mapped_column(String(20), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    aliases: Mapped[list] = mapped_column(
        ARRAY(Text), default=list, nullable=False
    )
    excerpt: Mapped[str | None] = mapped_column(Text, default=None)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    folder_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    updated_by_user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    generation_run_id: Mapped[int | None] = mapped_column(BigInteger, default=None)


class WikiPageLink(Base):
    """页面间由 wikilink 形成的有向边；由正文同步派生，可重建。"""

    __tablename__ = "wiki_page_links"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    from_page_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    to_page_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    target_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WikiPageDocumentRef(Base):
    """Wiki 页面到原始文档具体版本的文档级血缘。"""

    __tablename__ = "wiki_page_document_refs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    wiki_page_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    revision_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WikiPageEvidenceRef(Base):
    """Wiki 页面到具体 Revision 原文片段的证据级血缘。"""

    __tablename__ = "wiki_page_evidence_refs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    wiki_page_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    revision_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_locator: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    content_chunk_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
