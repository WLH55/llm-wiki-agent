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

    # 内部文件夹 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # API 使用的稳定公开 ID，全局唯一
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    # 文件夹所属 KB
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 父文件夹逻辑引用；NULL 表示 Wiki 根目录下的一级文件夹
    parent_id: Mapped[int | None] = mapped_column(BigInteger, default=None, index=True)
    # 用户可见名称，允许修改
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # 稳定且文件系统安全的 Markdown 导出路径段，创建后不可修改
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    # 同一父目录内的人工排序权重
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 移动、改名和排序时的乐观锁
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 创建者；系统创建时为空
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # 最近修改者；系统修改时为空
    updated_by_user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)


class WikiPage(Base, TimestampMixin, TenantMixin):
    """Wiki 页面；slug 创建后不可修改，改名只改 title/aliases。"""

    __tablename__ = "wiki_pages"

    # 内部关联 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # API 对外稳定页面 ID，全局唯一
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    # KB 逻辑引用
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # summary / entity / concept / index / log / synthesis / comparison
    page_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # KB 内稳定页面标识，用于 URL 与 wikilink，创建后不可修改
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    # 用户看到的页面标题
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    # 简称、旧称和中英文名称，只辅助搜索
    aliases: Mapped[list] = mapped_column(
        ARRAY(Text), default=list, nullable=False
    )
    # 页面简短预览，用于目录列表、搜索结果和 Agent 选页
    excerpt: Mapped[str | None] = mapped_column(Text, default=None)
    # 完整 Markdown 正文
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # 页面真实目录归属；NULL 表示 Wiki 根目录或无普通目录的系统页
    folder_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # 同一目录内的人工排序权重
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # 编辑乐观锁；成功修改后递增
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # 创建者；系统或 Agent 创建时为空
    created_by_user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # 最近一次人工修改者；系统更新时为空
    updated_by_user_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # 最近一次写入该页面的 Wiki 生成运行
    generation_run_id: Mapped[int | None] = mapped_column(BigInteger, default=None)


class WikiPageLink(Base):
    """页面间由 wikilink 形成的有向边；由正文同步派生，可重建。"""

    __tablename__ = "wiki_page_links"

    # 内部链接记录 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 租户隔离过滤
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # KB 逻辑引用与链接解析范围
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 发出 wikilink 的来源页面
    from_page_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 已解析目标页面；目标尚不存在或被软删除时为空
    to_page_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # Markdown 中声明的不可变目标 slug；用于悬空链接和后续自动解析
    target_slug: Mapped[str] = mapped_column(String(255), nullable=False)
    # 首次提取该链接的时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 链接解析状态更新时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class WikiPageDocumentRef(Base):
    """Wiki 页面到原始文档具体版本的文档级血缘。"""

    __tablename__ = "wiki_page_document_refs"

    # 内部来源关系 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 租户隔离过滤
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # KB 隔离过滤
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Wiki 页面逻辑引用
    wiki_page_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 稳定 Document 逻辑引用，用于文档导航和按文档反查页面
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 页面实际使用的不可变 Document Revision；文档产生新版时不自动漂移
    revision_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 当前来源关系建立时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WikiPageEvidenceRef(Base):
    """Wiki 页面到具体 Revision 原文片段的证据级血缘。"""

    __tablename__ = "wiki_page_evidence_refs"

    # 内部证据记录 ID
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # 租户隔离过滤
    tenant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # KB 隔离过滤
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # 使用这条证据的 Wiki 页面
    wiki_page_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 证据所属的稳定 Document
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 证据所属的具体不可变 Revision
    revision_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 应用从共享 chunk 中核验复制的准确原文；不得信任 AI 自由改写后写入
    evidence_quote: Mapped[str] = mapped_column(Text, nullable=False)
    # 对 Revision、规范化位置和规范化引用计算的指纹，用于消除重复证据
    evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # PDF 页码、标题路径、Excel sheet/行号、段落范围等原文位置
    source_locator: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # 生成证据时使用的共享 content_chunks 逻辑引用；该 chunk 删除后清空
    content_chunk_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    # 证据创建时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # 清空 content_chunk_id 等关联状态的更新时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
