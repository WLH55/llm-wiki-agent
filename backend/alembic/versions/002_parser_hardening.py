"""add parser production metadata

Revision ID: 002
Revises: 001
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "parser_engine",
            sa.String(length=50),
            server_default="builtin",
            nullable=False,
        ),
    )
    op.add_column(
        "documents",
        sa.Column("parse_error_code", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "parse_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("documents", "parse_metadata")
    op.drop_column("documents", "parse_error_code")
    op.drop_column("documents", "parser_engine")
