"""pg_search BM25 索引：创建 pg_search 扩展 + content_chunks BM25 索引

Revision ID: 003
Revises: 002
Create Date: 2026-08-12

设计依据：mydocs/specs/2026-08-06_17-43_RAG知识库检索设计.md（ADR-0019）

本次迁移配合 RAG 检索地基升级：
1. 创建 pg_search 扩展（ParadeDB 镜像内置，幂等）
2. 在 content_chunks 表上建 BM25 索引（chinese_lindera 中文分词）
   - 替代原 ILIKE demo 级关键词检索
   - 支持 text ||| :q 查询操作符 + paradedb.score(id) 打分

回滚（downgrade）删除 BM25 索引；pg_search 扩展保留（其他对象可能依赖）。
"""
from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """升级：创建 pg_search 扩展 + content_chunks BM25 索引。"""

    # ----- 1. 创建 pg_search 扩展（ParadeDB 镜像内置，幂等） -----
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")

    # ----- 2. content_chunks BM25 索引（chinese_lindera 中文分词） -----
    # key_field=id 用于 paradedb.score(id) 打分
    # text_fields 只索引 text 列，chinese_lindera 支持中文分词
    # 同时索引 kb_id/document_id/revision_id 用于 BM25 查询时的过滤
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS content_chunks_bm25_idx
        ON content_chunks
        USING bm25 (id, kb_id, text, document_id, revision_id)
        WITH (
            key_field = 'id',
            text_fields = '{"text": {"tokenizer": {"type": "chinese_lindera"}}}'
        )
        """
    )


def downgrade() -> None:
    """回滚：删除 BM25 索引（pg_search 扩展保留）。"""

    op.execute("DROP INDEX IF EXISTS content_chunks_bm25_idx")
