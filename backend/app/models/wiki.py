"""Wiki 知识整理域模型（4 张表）。"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, uuid_pk


class WikiFolder(TimestampMixin, SoftDeleteMixin, Base):
    """Wiki 目录树（邻接表），path 为物化路径；页面 folder_id 归属。"""

    __tablename__ = "wiki_folders"

    id: Mapped[str] = uuid_pk()
    # 0 = 系统/默认
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    knowledge_base_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # 父目录 ID（'' = 根）
    parent_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 物化路径（/ 连接名称链）
    path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class WikiPage(TimestampMixin, SoftDeleteMixin, Base):
    """Wiki 页面（知识整理产物）：目录归属、双向链接、来源引用（JSONB）。"""

    __tablename__ = "wiki_pages"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # 页面 slug（库内唯一路径）
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    # summary/entity/concept/index/log（log 已废弃）等
    page_type: Mapped[str] = mapped_column(String(32), nullable=False, default="summary")
    # published/draft/archived
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="published")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    parent_slug: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    # 所在目录 ID（'' = 根）
    folder_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    # 目录链
    category_path: Mapped[list | None] = mapped_column(JSONB, default=list)
    # 物化路径（如 /目录/子目录/页面）
    wiki_path: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # 来源引用
    source_refs: Mapped[list | None] = mapped_column(JSONB, default=list)
    # 引用块
    chunk_refs: Mapped[list | None] = mapped_column(JSONB, default=list)
    # 入链 / 出链（JSONB 数组）
    in_links: Mapped[list | None] = mapped_column(JSONB, default=list)
    out_links: Mapped[list | None] = mapped_column(JSONB, default=list)
    page_metadata: Mapped[dict | None] = mapped_column(JSONB, default=dict)
    aliases: Mapped[list | None] = mapped_column(JSONB, default=list)
    # 当前版本号
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # pipeline/agent/user/revert（'' = legacy，视作 pipeline）
    last_edit_source: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    last_editor_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class WikiPageRevision(Base):
    """Wiki 页面版本历史。"""

    __tablename__ = "wiki_page_revisions"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(36), nullable=False)
    page_id: Mapped[str] = mapped_column(String(36), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    page_type: Mapped[str] = mapped_column(String(32), nullable=False, default="summary")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="published")
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    aliases: Mapped[list | None] = mapped_column(JSONB, default=list)
    # user / wiki / api
    edit_source: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    editor_id: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    edited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WikiPageIssue(TimestampMixin, SoftDeleteMixin, Base):
    """Wiki 页面质量问题上报（content-error/missing-info 等）。"""

    __tablename__ = "wiki_page_issues"

    id: Mapped[str] = uuid_pk()
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    knowledge_base_id: Mapped[str] = mapped_column(String(36), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # 疑似相关知识 ID 列表
    suspected_knowledge_ids: Mapped[list | None] = mapped_column(JSONB)
    # pending / resolved
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    reported_by: Mapped[str] = mapped_column(String(100), nullable=False)
