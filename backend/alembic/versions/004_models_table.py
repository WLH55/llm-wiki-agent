"""models 表 + KB 绑定模型字段

Revision ID: 004
Revises: 003
Create Date: 2026-08-12

设计依据：mydocs/specs/2026-08-11_17-00_生成集成设计.md（ADR-0020/0021）

本次迁移为 P1 生成集成铺路：
1. 新建 models 表（工作区级模型配置，照搬 WeKnora 设计）
   - parameters JSONB 承载厂商配置（base_url / 加密 api_key / 模型名等）
   - model_type: chat | embedding
   - api_key 用 AES-256-GCM 加密后存 parameters（加密逻辑在 app/core/crypto.py）
2. knowledge_bases 新增 embedding_model_id + chat_model_id（逻辑引用，无 DB 外键，
   与全库"不建外键"决策一致）；DB 层 nullable，必填由应用层校验（存量 KB 行兼容）

回滚（downgrade）删除两列与 models 表。
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """升级：创建 models 表 + KB 表加模型绑定列。"""

    # ----- 1. models 表（工作区级模型配置） -----
    op.create_table(
        "models",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("tenant_id", sa.BigInteger, nullable=False),
        # 用户可见的配置名，如 deepseek-v4-flash / jina-embeddings-v5-text-small
        sa.Column("name", sa.String(200), nullable=False),
        # chat | embedding（P3 加 rerank）
        sa.Column("model_type", sa.String(50), nullable=False),
        # 协议来源：openai（OpenAI 兼容协议）
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        # 厂商配置：base_url / api_key(AES-256-GCM 加密) / model_name / timeout_seconds
        sa.Column("parameters", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_models_tenant_id", "models", ["tenant_id"])

    # ----- 2. KB 表加模型绑定列（逻辑引用，应用层校验必填） -----
    op.add_column("knowledge_bases", sa.Column("embedding_model_id", sa.BigInteger, nullable=True))
    op.add_column("knowledge_bases", sa.Column("chat_model_id", sa.BigInteger, nullable=True))
    op.create_index("ix_knowledge_bases_embedding_model_id", "knowledge_bases", ["embedding_model_id"])
    op.create_index("ix_knowledge_bases_chat_model_id", "knowledge_bases", ["chat_model_id"])


def downgrade() -> None:
    """回滚：删 KB 绑定列 + models 表。"""

    op.drop_index("ix_knowledge_bases_chat_model_id", table_name="knowledge_bases")
    op.drop_index("ix_knowledge_bases_embedding_model_id", table_name="knowledge_bases")
    op.drop_column("knowledge_bases", "chat_model_id")
    op.drop_column("knowledge_bases", "embedding_model_id")

    op.drop_index("ix_models_tenant_id", table_name="models")
    op.drop_table("models")
