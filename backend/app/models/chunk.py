"""
ContentChunk model

注意：
- embedding: halfvec(不带 N)，DDL 在 migration 手写（SQLAlchemy 不直接支持 halfvec）
- search_vector: tsvector，DDL 在 migration 手写
- search_vector 由 PG trigger 自动维护（INSERT/UPDATE 时 tsvector_update_trigger）

【关键陷阱】：查询 SQL 必须将 embedding cast 成 halfvec(N)，
否则规划器认不出 partial HNSW 索引会退化全表扫（参 ADR-0001）。
"""
from typing import Optional
from uuid import UUID

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class ContentChunk(Base, TimestampMixin, TenantMixin):
    """内容块（向量 + 全文双索引）"""
    __tablename__ = "content_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(nullable=False, index=True)
    doc_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    source_id: Mapped[Optional[int]] = mapped_column(default=None, index=True)

    chunk_type: Mapped[str] = mapped_column(
        String(50), default="document", nullable=False
    )  # document / wiki_page / image_ocr / image_caption

    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)

    wiki_page_id: Mapped[Optional[int]] = mapped_column(default=None, index=True)

    # embedding: halfvec 列（DDL 在 migration 手写）
    # search_vector: tsvector 列（DDL 在 migration 手写）
