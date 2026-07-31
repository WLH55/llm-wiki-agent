"""make active manual sources unique per tenant and knowledge base

Revision ID: 005
Revises: 004
Create Date: 2026-07-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "005"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """合并历史重复 manual Source，并为并发上传建立数据库级约束。"""
    op.execute(
        """
        WITH duplicate_sources AS (
            SELECT id,
                   min(id) OVER (PARTITION BY tenant_id, kb_id, source_type) AS canonical_id
            FROM sources
            WHERE source_type = 'manual' AND deleted_at IS NULL
        )
        UPDATE documents d
        SET source_id = duplicates.canonical_id
        FROM duplicate_sources duplicates
        WHERE d.source_id = duplicates.id
          AND duplicates.id <> duplicates.canonical_id
        """
    )
    op.execute(
        """
        WITH duplicate_sources AS (
            SELECT id,
                   min(id) OVER (PARTITION BY tenant_id, kb_id, source_type) AS canonical_id
            FROM sources
            WHERE source_type = 'manual' AND deleted_at IS NULL
        )
        UPDATE content_chunks c
        SET source_id = duplicates.canonical_id
        FROM duplicate_sources duplicates
        WHERE c.source_id = duplicates.id
          AND duplicates.id <> duplicates.canonical_id
        """
    )
    op.execute(
        """
        WITH duplicate_sources AS (
            SELECT id,
                   min(id) OVER (PARTITION BY tenant_id, kb_id, source_type) AS canonical_id
            FROM sources
            WHERE source_type = 'manual' AND deleted_at IS NULL
        )
        DELETE FROM sources s
        USING duplicate_sources duplicates
        WHERE s.id = duplicates.id
          AND duplicates.id <> duplicates.canonical_id
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_sources_manual_active_per_kb
            ON sources (tenant_id, kb_id, source_type)
            WHERE source_type = 'manual' AND deleted_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_sources_manual_active_per_kb")
