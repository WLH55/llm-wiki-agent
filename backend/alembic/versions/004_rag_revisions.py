"""add revision-based RAG ingestion and activation contract

Revision ID: 004
Revises: 003
Create Date: 2026-07-31
"""

from collections.abc import Sequence

from alembic import op

revision: str = "004"
down_revision: str | None = "003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _execute_script(script: str) -> None:
    """asyncpg 只接受单条 prepared statement，迁移事务内逐句执行。"""
    for statement in script.split(";"):
        if statement.strip():
            op.execute(statement)


def upgrade() -> None:
    """增加候选 Revision、独立 RAG 配置及两阶段激活所需字段。"""
    _execute_script(
        """
        ALTER TABLE knowledge_bases
            ADD COLUMN public_id UUID DEFAULT gen_random_uuid(),
            ADD COLUMN chunking_strategy VARCHAR(50) NOT NULL DEFAULT 'recursive_tokens',
            ADD COLUMN chunk_size_tokens INTEGER NOT NULL DEFAULT 300,
            ADD COLUMN chunk_overlap_tokens INTEGER NOT NULL DEFAULT 50,
            ADD COLUMN chunking_options JSONB NOT NULL DEFAULT '{}'::jsonb,
            ADD COLUMN chunking_config_version INTEGER NOT NULL DEFAULT 1;
        UPDATE knowledge_bases SET public_id = gen_random_uuid() WHERE public_id IS NULL;
        ALTER TABLE knowledge_bases ALTER COLUMN public_id SET NOT NULL;
        CREATE UNIQUE INDEX uq_knowledge_bases_public_id ON knowledge_bases(public_id);
        ALTER TABLE knowledge_bases ADD CONSTRAINT ck_knowledge_bases_chunking_budget
            CHECK (
                chunk_size_tokens > 0
                AND chunk_overlap_tokens >= 0
                AND chunk_overlap_tokens < chunk_size_tokens
                AND chunking_config_version >= 1
            );
        """
    )
    _execute_script(
        """
        CREATE TABLE kb_rag_configs (
            kb_id BIGINT PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            vector_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            keyword_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            embedding_model_key VARCHAR(200),
            embedding_dim INTEGER,
            config_version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_kb_rag_configs_retrieval CHECK (
                NOT enabled OR vector_enabled OR keyword_enabled
            ),
            CONSTRAINT ck_kb_rag_configs_embedding CHECK (
                NOT vector_enabled
                OR (embedding_model_key IS NOT NULL AND embedding_dim > 0)
            ),
            CONSTRAINT ck_kb_rag_configs_version CHECK (config_version >= 1)
        );
        INSERT INTO kb_rag_configs (
            kb_id, enabled, vector_enabled, keyword_enabled,
            embedding_model_key, embedding_dim
        )
        SELECT id, TRUE, vector_enabled, keyword_enabled,
               CASE WHEN vector_enabled THEN embedding_model ELSE NULL END,
               CASE WHEN vector_enabled THEN embedding_dim ELSE NULL END
        FROM knowledge_bases;
        """
    )
    _execute_script(
        """
        ALTER TABLE sources
            ADD COLUMN public_id UUID DEFAULT gen_random_uuid(),
            ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN config_version INTEGER NOT NULL DEFAULT 1,
            ADD COLUMN last_synced_at TIMESTAMPTZ;
        UPDATE sources SET public_id = gen_random_uuid() WHERE public_id IS NULL;
        ALTER TABLE sources ALTER COLUMN public_id SET NOT NULL;
        CREATE UNIQUE INDEX uq_sources_public_id ON sources(public_id);
        """
    )
    _execute_script(
        """
        INSERT INTO sources (tenant_id, kb_id, source_type, name, config, sync_cursor)
        SELECT DISTINCT d.tenant_id, d.kb_id, 'manual', 'Manual uploads', '{}'::jsonb, ''
        FROM documents d
        WHERE d.source_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM sources s
              WHERE s.kb_id = d.kb_id AND s.source_type = 'manual'
          );
        UPDATE documents d
        SET source_id = (
            SELECT min(s.id) FROM sources s
            WHERE s.kb_id = d.kb_id AND s.source_type = 'manual'
        )
        WHERE d.source_id IS NULL;
        """
    )
    _execute_script(
        """
        ALTER TABLE documents
            ADD COLUMN public_id UUID,
            ADD COLUMN source_document_key VARCHAR(512),
            ADD COLUMN title VARCHAR(500),
            ADD COLUMN active_revision_id BIGINT,
            ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
        UPDATE documents
        SET public_id = doc_id,
            source_document_key = doc_id::text,
            title = original_filename;
        ALTER TABLE documents
            ALTER COLUMN public_id SET NOT NULL,
            ALTER COLUMN source_document_key SET NOT NULL,
            ALTER COLUMN title SET NOT NULL;
        CREATE UNIQUE INDEX uq_documents_public_id ON documents(public_id);
        CREATE UNIQUE INDEX uq_documents_source_key_active
            ON documents(source_id, source_document_key) WHERE deleted_at IS NULL;
        CREATE INDEX ix_documents_active_revision_id ON documents(active_revision_id);
        """
    )
    _execute_script(
        """
        CREATE TABLE document_revisions (
            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            document_id BIGINT NOT NULL,
            revision_no INTEGER NOT NULL CHECK (revision_no >= 1),
            source_version VARCHAR(255),
            source_updated_at TIMESTAMPTZ,
            original_filename VARCHAR(500) NOT NULL,
            media_type VARCHAR(255) NOT NULL,
            size_bytes BIGINT NOT NULL CHECK (size_bytes >= 0),
            content_sha256 CHAR(64) NOT NULL,
            storage_key VARCHAR(1000) NOT NULL,
            parser_engine VARCHAR(50) NOT NULL DEFAULT 'builtin',
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            parse_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_by_user_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            deleted_at TIMESTAMPTZ,
            CONSTRAINT uq_document_revisions_number UNIQUE (document_id, revision_no),
            CONSTRAINT uq_document_revisions_storage_key UNIQUE (storage_key),
            CONSTRAINT ck_document_revisions_status
                CHECK (status IN ('pending', 'processing', 'ready', 'failed')),
            CONSTRAINT ck_document_revisions_sha256
                CHECK (content_sha256 ~ '^[0-9a-f]{64}$')
        );
        CREATE UNIQUE INDEX uq_document_revisions_source_version_active
            ON document_revisions(document_id, source_version)
            WHERE source_version IS NOT NULL AND deleted_at IS NULL;
        CREATE INDEX ix_document_revisions_document ON document_revisions(document_id);
        CREATE INDEX ix_document_revisions_content_sha256 ON document_revisions(content_sha256);

        INSERT INTO document_revisions (
            document_id, revision_no, original_filename, media_type, size_bytes,
            content_sha256, storage_key, parser_engine, status, parse_metadata,
            created_at, updated_at, deleted_at
        )
        SELECT id, 1, original_filename, 'application/octet-stream', 0,
               md5(doc_id::text) || md5(doc_id::text), minio_key, parser_engine,
               CASE status
                   WHEN 'processed' THEN 'ready'
                   WHEN 'processing' THEN 'failed'
                   WHEN 'failed' THEN 'failed'
                   ELSE 'pending'
               END,
               parse_metadata, created_at, updated_at, deleted_at
        FROM documents;
        """
    )
    _execute_script(
        """
        INSERT INTO processing_runs (
            tenant_id, kb_id, run_type, scope_type, scope_id, trigger_type,
            status, options_snapshot, error_code, error_message,
            started_at, heartbeat_at, finished_at, created_at, updated_at
        )
        SELECT d.tenant_id, d.kb_id, 'document_process', 'revision', r.id, 'manual',
               CASE r.status
                   WHEN 'ready' THEN 'succeeded'
                   WHEN 'failed' THEN 'failed'
                   ELSE 'pending'
               END,
               '{"legacy_backfill": true}'::jsonb,
               CASE WHEN r.status = 'failed' THEN 'legacy_restart_required' END,
               CASE WHEN r.status = 'failed' THEN 'legacy processing state migrated' END,
               CASE WHEN r.status IN ('ready', 'failed') THEN r.created_at END,
               CASE WHEN r.status IN ('ready', 'failed') THEN r.updated_at END,
               CASE WHEN r.status IN ('ready', 'failed') THEN r.updated_at END,
               r.created_at, r.updated_at
        FROM document_revisions r
        JOIN documents d ON d.id = r.document_id;
        """
    )
    _execute_script(
        """
        ALTER TABLE content_chunks
            ADD COLUMN public_id UUID DEFAULT gen_random_uuid(),
            ADD COLUMN document_id BIGINT,
            ADD COLUMN revision_id BIGINT,
            ADD COLUMN processing_run_id BIGINT,
            ADD COLUMN embedding_run_id BIGINT,
            ADD COLUMN chunk_index INTEGER,
            ADD COLUMN token_count INTEGER,
            ADD COLUMN text_sha256 CHAR(64),
            ADD COLUMN source_locator JSONB NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE content_chunks ALTER COLUMN embedding DROP NOT NULL;
        ALTER TABLE content_chunks ALTER COLUMN embedding_dim DROP NOT NULL;

        WITH ranked AS (
            SELECT c.id, d.id AS document_id, r.id AS revision_id,
                   row_number() OVER (PARTITION BY d.id ORDER BY c.id) - 1 AS chunk_index
            FROM content_chunks c
            JOIN documents d ON d.doc_id = c.doc_id
            JOIN document_revisions r ON r.document_id = d.id AND r.revision_no = 1
        )
        UPDATE content_chunks c
        SET document_id = ranked.document_id,
            revision_id = ranked.revision_id,
            chunk_index = ranked.chunk_index,
            token_count = GREATEST(1, length(c.text) / 4),
            text_sha256 = md5(c.text) || md5(c.text)
        FROM ranked
        WHERE c.id = ranked.id;

        UPDATE content_chunks c
        SET processing_run_id = pr.id
        FROM processing_runs pr
        WHERE pr.run_type = 'document_process'
          AND pr.scope_type = 'revision'
          AND pr.scope_id = c.revision_id
          AND pr.options_snapshot @> '{"legacy_backfill": true}'::jsonb;

        INSERT INTO processing_runs (
            tenant_id, kb_id, run_type, scope_type, scope_id, parent_run_id,
            trigger_type, status, options_snapshot, started_at, heartbeat_at,
            finished_at, created_at, updated_at
        )
        SELECT d.tenant_id, d.kb_id, 'rag_index', 'revision', r.id, parent.id,
               'on_ingest', 'succeeded', '{"legacy_backfill": true}'::jsonb,
               r.created_at, r.updated_at, r.updated_at, r.created_at, r.updated_at
        FROM document_revisions r
        JOIN documents d ON d.id = r.document_id
        JOIN processing_runs parent
          ON parent.run_type = 'document_process'
         AND parent.scope_type = 'revision'
         AND parent.scope_id = r.id
         AND parent.options_snapshot @> '{"legacy_backfill": true}'::jsonb
        WHERE EXISTS (
            SELECT 1 FROM content_chunks c
            WHERE c.revision_id = r.id AND c.embedding IS NOT NULL
        );

        UPDATE content_chunks c
        SET embedding_run_id = pr.id
        FROM processing_runs pr
        WHERE c.embedding IS NOT NULL
          AND pr.run_type = 'rag_index'
          AND pr.scope_type = 'revision'
          AND pr.scope_id = c.revision_id
          AND pr.options_snapshot @> '{"legacy_backfill": true}'::jsonb;

        ALTER TABLE content_chunks
            ALTER COLUMN public_id SET NOT NULL,
            ALTER COLUMN document_id SET NOT NULL,
            ALTER COLUMN revision_id SET NOT NULL,
            ALTER COLUMN processing_run_id SET NOT NULL,
            ALTER COLUMN chunk_index SET NOT NULL,
            ALTER COLUMN token_count SET NOT NULL,
            ALTER COLUMN text_sha256 SET NOT NULL;
        CREATE UNIQUE INDEX uq_content_chunks_public_id ON content_chunks(public_id);
        ALTER TABLE content_chunks
            ADD CONSTRAINT uq_content_chunks_revision_index UNIQUE (revision_id, chunk_index),
            ADD CONSTRAINT ck_content_chunks_nonempty_text CHECK (length(btrim(text)) > 0),
            ADD CONSTRAINT ck_content_chunks_chunk_index CHECK (chunk_index >= 0),
            ADD CONSTRAINT ck_content_chunks_token_count CHECK (token_count >= 0),
            ADD CONSTRAINT ck_content_chunks_embedding_shape CHECK (
                (embedding IS NULL AND embedding_dim IS NULL AND embedding_run_id IS NULL)
                OR
                (embedding IS NOT NULL AND embedding_dim > 0 AND embedding_run_id IS NOT NULL)
            );
        CREATE INDEX ix_content_chunks_tenant_kb_v2 ON content_chunks(tenant_id, kb_id);
        CREATE INDEX ix_content_chunks_document_index ON content_chunks(document_id, chunk_index);
        CREATE INDEX ix_content_chunks_revision_index ON content_chunks(revision_id, chunk_index);
        CREATE INDEX ix_content_chunks_processing_run ON content_chunks(processing_run_id);
        CREATE INDEX ix_content_chunks_embedding_run
            ON content_chunks(embedding_run_id) WHERE embedding_run_id IS NOT NULL;

        UPDATE documents d
        SET active_revision_id = r.id
        FROM document_revisions r
        WHERE r.document_id = d.id AND r.status = 'ready' AND d.status = 'processed';
        """
    )


def downgrade() -> None:
    """移除 Revision 契约；空向量候选 chunk 无法回到旧 schema，会先清理。"""
    _execute_script(
        """
        DELETE FROM content_chunks WHERE embedding IS NULL;
        DROP INDEX IF EXISTS ix_content_chunks_embedding_run;
        DROP INDEX IF EXISTS ix_content_chunks_processing_run;
        DROP INDEX IF EXISTS ix_content_chunks_revision_index;
        DROP INDEX IF EXISTS ix_content_chunks_document_index;
        DROP INDEX IF EXISTS ix_content_chunks_tenant_kb_v2;
        DROP INDEX IF EXISTS uq_content_chunks_public_id;
        ALTER TABLE content_chunks
            DROP CONSTRAINT IF EXISTS ck_content_chunks_embedding_shape,
            DROP CONSTRAINT IF EXISTS ck_content_chunks_token_count,
            DROP CONSTRAINT IF EXISTS ck_content_chunks_chunk_index,
            DROP CONSTRAINT IF EXISTS ck_content_chunks_nonempty_text,
            DROP CONSTRAINT IF EXISTS uq_content_chunks_revision_index;
        ALTER TABLE content_chunks
            DROP COLUMN IF EXISTS source_locator,
            DROP COLUMN IF EXISTS text_sha256,
            DROP COLUMN IF EXISTS token_count,
            DROP COLUMN IF EXISTS chunk_index,
            DROP COLUMN IF EXISTS embedding_run_id,
            DROP COLUMN IF EXISTS processing_run_id,
            DROP COLUMN IF EXISTS revision_id,
            DROP COLUMN IF EXISTS document_id,
            DROP COLUMN IF EXISTS public_id;
        ALTER TABLE content_chunks ALTER COLUMN embedding SET NOT NULL;
        ALTER TABLE content_chunks ALTER COLUMN embedding_dim SET NOT NULL;

        DELETE FROM processing_runs
        WHERE options_snapshot @> '{"legacy_backfill": true}'::jsonb;

        DROP INDEX IF EXISTS ix_documents_active_revision_id;
        DROP INDEX IF EXISTS uq_documents_source_key_active;
        DROP INDEX IF EXISTS uq_documents_public_id;
        ALTER TABLE documents
            DROP COLUMN IF EXISTS version,
            DROP COLUMN IF EXISTS active_revision_id,
            DROP COLUMN IF EXISTS title,
            DROP COLUMN IF EXISTS source_document_key,
            DROP COLUMN IF EXISTS public_id;

        DROP TABLE IF EXISTS document_revisions;
        DROP INDEX IF EXISTS uq_sources_public_id;
        ALTER TABLE sources
            DROP COLUMN IF EXISTS last_synced_at,
            DROP COLUMN IF EXISTS config_version,
            DROP COLUMN IF EXISTS enabled,
            DROP COLUMN IF EXISTS public_id;
        DROP TABLE IF EXISTS kb_rag_configs;
        ALTER TABLE knowledge_bases DROP CONSTRAINT IF EXISTS ck_knowledge_bases_chunking_budget;
        DROP INDEX IF EXISTS uq_knowledge_bases_public_id;
        ALTER TABLE knowledge_bases
            DROP COLUMN IF EXISTS chunking_config_version,
            DROP COLUMN IF EXISTS chunking_options,
            DROP COLUMN IF EXISTS chunk_overlap_tokens,
            DROP COLUMN IF EXISTS chunk_size_tokens,
            DROP COLUMN IF EXISTS chunking_strategy,
            DROP COLUMN IF EXISTS public_id;
        """
    )
