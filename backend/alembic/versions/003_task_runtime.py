"""add reliable task runtime tables

Revision ID: 003
Revises: 002
Create Date: 2026-07-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "003"
down_revision: str | None = "002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """创建 Run/Span、执行租约和持久化投递 Outbox。"""
    op.execute(
        """
        CREATE TABLE processing_runs (
            id BIGSERIAL PRIMARY KEY,
            public_id UUID NOT NULL DEFAULT gen_random_uuid(),
            tenant_id BIGINT NOT NULL,
            kb_id BIGINT NOT NULL,
            run_type VARCHAR(50) NOT NULL,
            scope_type VARCHAR(30) NOT NULL,
            scope_id BIGINT NOT NULL,
            parent_run_id BIGINT,
            retry_of_run_id BIGINT,
            attempt_no INTEGER NOT NULL DEFAULT 1 CHECK (attempt_no >= 1),
            trigger_type VARCHAR(20) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            idempotency_key VARCHAR(255),
            effective_config_version INTEGER CHECK (effective_config_version IS NULL OR effective_config_version >= 1),
            options_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            requested_by_user_id BIGINT,
            error_code VARCHAR(50),
            error_message VARCHAR(1000),
            execution_token UUID,
            execution_epoch INTEGER NOT NULL DEFAULT 0 CHECK (execution_epoch >= 0),
            lease_expires_at TIMESTAMPTZ,
            worker_id VARCHAR(255),
            started_at TIMESTAMPTZ,
            heartbeat_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_processing_runs_public_id UNIQUE (public_id),
            CONSTRAINT ck_processing_runs_status CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'cancelled')),
            CONSTRAINT ck_processing_runs_lease_shape CHECK (
                (execution_token IS NULL AND lease_expires_at IS NULL AND worker_id IS NULL)
                OR
                (execution_token IS NOT NULL AND lease_expires_at IS NOT NULL AND worker_id IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_processing_runs_idempotency ON processing_runs(tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_processing_runs_tenant_kb_created ON processing_runs(tenant_id, kb_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_processing_runs_type_status_created ON processing_runs(run_type, status, created_at)"
    )
    op.execute(
        "CREATE INDEX ix_processing_runs_scope_created ON processing_runs(scope_type, scope_id, created_at DESC)"
    )
    op.execute("CREATE INDEX ix_processing_runs_parent ON processing_runs(parent_run_id)")
    op.execute("CREATE INDEX ix_processing_runs_retry ON processing_runs(retry_of_run_id)")
    op.execute(
        "CREATE INDEX ix_processing_runs_status_heartbeat ON processing_runs(status, heartbeat_at)"
    )
    op.execute(
        "CREATE INDEX ix_processing_runs_status_lease ON processing_runs(status, lease_expires_at)"
    )
    op.execute(
        """
        CREATE TABLE processing_spans (
            id BIGSERIAL PRIMARY KEY,
            public_id UUID NOT NULL DEFAULT gen_random_uuid(),
            tenant_id BIGINT NOT NULL,
            kb_id BIGINT NOT NULL,
            run_id BIGINT NOT NULL,
            parent_span_id BIGINT,
            span_name VARCHAR(50) NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            model_key VARCHAR(200),
            input_tokens BIGINT CHECK (input_tokens IS NULL OR input_tokens >= 0),
            output_tokens BIGINT CHECK (output_tokens IS NULL OR output_tokens >= 0),
            metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_code VARCHAR(50),
            error_message VARCHAR(1000),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_processing_spans_public_id UNIQUE (public_id),
            CONSTRAINT ck_processing_spans_status CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'skipped', 'cancelled'))
        )
        """
    )
    op.execute("CREATE INDEX ix_processing_spans_tenant_kb ON processing_spans(tenant_id, kb_id)")
    op.execute("CREATE INDEX ix_processing_spans_run_created ON processing_spans(run_id, created_at, id)")
    op.execute("CREATE INDEX ix_processing_spans_parent ON processing_spans(parent_span_id)")
    op.execute("CREATE INDEX ix_processing_spans_status_started ON processing_spans(status, started_at)")
    op.execute("CREATE INDEX ix_processing_spans_model_started ON processing_spans(model_key, started_at)")
    op.execute(
        """
        CREATE TABLE task_outbox (
            id BIGSERIAL PRIMARY KEY,
            run_id BIGINT NOT NULL,
            task_name VARCHAR(100) NOT NULL,
            queue_name VARCHAR(50) NOT NULL,
            available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            publish_attempts INTEGER NOT NULL DEFAULT 0 CHECK (publish_attempts >= 0),
            lock_token UUID,
            locked_until TIMESTAMPTZ,
            published_at TIMESTAMPTZ,
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_task_outbox_lock_shape CHECK (
                (lock_token IS NULL AND locked_until IS NULL)
                OR
                (lock_token IS NOT NULL AND locked_until IS NOT NULL)
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_task_outbox_ready ON task_outbox(available_at, id) WHERE published_at IS NULL"
    )
    op.execute("CREATE INDEX ix_task_outbox_run ON task_outbox(run_id, id DESC)")
    op.execute(
        "CREATE INDEX ix_task_outbox_lock ON task_outbox(locked_until) WHERE published_at IS NULL"
    )


def downgrade() -> None:
    """删除任务运行支撑表。"""
    op.execute("DROP TABLE IF EXISTS task_outbox")
    op.execute("DROP TABLE IF EXISTS processing_spans")
    op.execute("DROP TABLE IF EXISTS processing_runs")
