"""
ContentChunk model

按 2026-08-02 定稿 spec 重建：
- 删除 doc_id / chunk_type / search_vector / wiki_page_id / deleted_at（spec 决策#7、
  content_chunks 字段边界：不保留 chunk_type / wiki_page_id / is_active / deleted_at /
  search_vector）。
- source_id 改 NOT NULL；类型统一 BigInteger。
- 本表只保留 created_at / updated_at，不带 deleted_at，故不使用 TimestampMixin。

注意：
- embedding: halfvec（不带 N），DDL 在 migration 手写（SQLAlchemy 不直接支持 halfvec）
- 【关键陷阱】：查询 SQL 必须将 embedding cast 成 halfvec(N)，否则规划器认不出
  partial HNSW 索引会退化全表扫（参 ADR-0001）。
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin


class ContentChunk(Base, TenantMixin):
    """共享内容块（RAG 召回单元 + Wiki Map 输入）；不带软删除。"""
    __tablename__ = "content_chunks"

    # 内部 ID，也是后续 pg_search BM25 的 key_field
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # API 对外 chunk ID，全局唯一
    public_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), default=uuid4, nullable=False, unique=True
    )
    # KB 过滤
    kb_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 来源过滤
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 逻辑文档引用
    document_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 生效文档版本引用
    revision_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 解析并生成本共享 chunk 的 document_process Run
    processing_run_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    # 最近一次写入当前 embedding 的 rag_index Run；未向量化时为空
    embedding_run_id: Mapped[int | None] = mapped_column(
        BigInteger, default=None, index=True
    )
    # 文档内从 0 开始的顺序
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # 共享原文块；同时作为 BM25 原文、embedding 输入和 Wiki Map 输入
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # 上下文 token 预算
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    # 文本指纹，用于 embedding 缓存与重复检测
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    # PDF 页码、Excel sheet/行号、Markdown 标题路径等原文位置
    source_locator: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    # 与 embedding 同时为空或同时存在
    embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 生成时间
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # embedding 写入或重建的最近更新时间
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # embedding: halfvec 列（DDL 在 migration 手写）
