"""initial schema: core tables + reserved tables + pgvector + zhparser

Revision ID: 001
Revises:
Create Date: 2026-07-10

包含：
1. CREATE EXTENSION vector + zhparser
2. CREATE TEXT SEARCH CONFIGURATION chinese_zh
3. 核心表：tenants / users / knowledge_bases / sources / documents / content_chunks
4. 空表预留（P2+）：organizations / org_members / kb_shares / llm_providers /
   user_llm_keys / wiki_folders / wiki_pages
5. content_chunks 的 embedding（halfvec，不带 N）+ search_vector（tsvector）
6. partial HNSW 索引（按 embedding_dim 分维度）
7. GIN 索引 over search_vector
8. search_vector trigger（自动维护 tsvector）
"""
from typing import Sequence, Union

from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """升级：创建所有表 + 扩展 + 索引 + trigger"""

    # ========== 1. 扩展 ==========
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS zhparser")

    # ========== 2. 中文分词配置 ==========
    op.execute("CREATE TEXT SEARCH CONFIGURATION chinese_zh (PARSER = zhparser)")
    op.execute(
        "ALTER TEXT SEARCH CONFIGURATION chinese_zh "
        "ADD MAPPING FOR n,v,a,i,e,j WITH simple"
    )

    # ========== 3. 核心表 ==========
    # 用 raw SQL 精确控制 DDL（halfvec / tsvector 需要原生 PG 类型）

    op.execute("""
    CREATE TABLE tenants (
        id              SERIAL PRIMARY KEY,
        name            VARCHAR(100) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at      TIMESTAMPTZ
    )
    """)

    op.execute("""
    CREATE TABLE users (
        id              SERIAL PRIMARY KEY,
        tenant_id       INT NOT NULL REFERENCES tenants(id),
        email           VARCHAR(255) NOT NULL UNIQUE,
        password_hash   VARCHAR(255) NOT NULL,
        role            VARCHAR(50) NOT NULL DEFAULT 'owner',
        is_active       BOOLEAN NOT NULL DEFAULT TRUE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at      TIMESTAMPTZ
    )
    """)
    op.execute("CREATE INDEX ix_users_tenant_id ON users(tenant_id) WHERE deleted_at IS NULL")

    op.execute("""
    CREATE TABLE knowledge_bases (
        id                SERIAL PRIMARY KEY,
        tenant_id         INT NOT NULL REFERENCES tenants(id),
        name              VARCHAR(200) NOT NULL,
        description       VARCHAR(1000) NOT NULL DEFAULT '',
        embedding_model   VARCHAR(100) NOT NULL,
        embedding_dim     INT NOT NULL,
        vector_enabled    BOOLEAN NOT NULL DEFAULT TRUE,
        keyword_enabled   BOOLEAN NOT NULL DEFAULT TRUE,
        wiki_enabled      BOOLEAN NOT NULL DEFAULT TRUE,
        graph_enabled     BOOLEAN NOT NULL DEFAULT FALSE,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at        TIMESTAMPTZ
    )
    """)
    op.execute("CREATE INDEX ix_knowledge_bases_tenant_id ON knowledge_bases(tenant_id) WHERE deleted_at IS NULL")

    op.execute("""
    CREATE TABLE sources (
        id              SERIAL PRIMARY KEY,
        tenant_id       INT NOT NULL REFERENCES tenants(id),
        kb_id           INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
        source_type     VARCHAR(50) NOT NULL DEFAULT 'manual',
        name            VARCHAR(255) NOT NULL DEFAULT '',
        config          JSONB NOT NULL DEFAULT '{}'::jsonb,
        sync_cursor     VARCHAR(500) NOT NULL DEFAULT '',
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at      TIMESTAMPTZ
    )
    """)
    op.execute("CREATE INDEX ix_sources_tenant_id ON sources(tenant_id) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_sources_kb_id ON sources(kb_id) WHERE deleted_at IS NULL")

    op.execute("""
    CREATE TABLE documents (
        id                SERIAL PRIMARY KEY,
        tenant_id         INT NOT NULL REFERENCES tenants(id),
        kb_id             INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
        source_id         INT REFERENCES sources(id) ON DELETE SET NULL,
        doc_id            UUID NOT NULL UNIQUE,
        original_filename VARCHAR(500) NOT NULL,
        minio_key         VARCHAR(500) NOT NULL,
        status            VARCHAR(50) NOT NULL DEFAULT 'pending',
        error_message     VARCHAR(1000) NOT NULL DEFAULT '',
        processed_at      TIMESTAMPTZ,
        created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at        TIMESTAMPTZ
    )
    """)
    op.execute("CREATE INDEX ix_documents_tenant_id ON documents(tenant_id) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_documents_kb_id ON documents(kb_id) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_documents_doc_id ON documents(doc_id) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_documents_status ON documents(status) WHERE deleted_at IS NULL")

    # ========== 4. content_chunks（核心表，halfvec + tsvector） ==========
    op.execute("""
    CREATE TABLE content_chunks (
        id              BIGSERIAL PRIMARY KEY,
        tenant_id       INT NOT NULL REFERENCES tenants(id),
        kb_id           INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
        doc_id          UUID NOT NULL,
        source_id       INT REFERENCES sources(id) ON DELETE SET NULL,
        chunk_type      TEXT NOT NULL DEFAULT 'document',
        text            TEXT NOT NULL,
        embedding       halfvec NOT NULL,
        embedding_dim   INT NOT NULL,
        search_vector   tsvector,
        wiki_page_id    INT REFERENCES wiki_pages(id) ON DELETE CASCADE,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at      TIMESTAMPTZ
    )
    """)

    # 注意：wiki_pages 表在下面才创建，content_chunks.wiki_page_id 引用它，
    # PG 允许 forward reference（DEFERRABLE），但稳妥起见用 ALTER 添加外键
    op.execute("""
    ALTER TABLE content_chunks DROP CONSTRAINT IF EXISTS content_chunks_wiki_page_id_fkey
    """)
    # wiki_pages 表在后面创建后再加 FK

    # ========== 5. partial HNSW 索引（按维度分） ==========
    # 1024 维（bge-m3 默认）
    op.execute("""
    CREATE INDEX content_chunks_embedding_1024_hnsw
        ON content_chunks
        USING hnsw ((embedding::halfvec(1024)) halfvec_cosine_ops)
        WHERE embedding_dim = 1024 AND deleted_at IS NULL
    """)

    # ========== 6. GIN 索引 over search_vector ==========
    op.execute("""
    CREATE INDEX content_chunks_search_vector_gin
        ON content_chunks USING gin(search_vector)
        WHERE deleted_at IS NULL
    """)

    # ========== 7. 业务索引 ==========
    op.execute("CREATE INDEX ix_content_chunks_tenant_id ON content_chunks(tenant_id) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_content_chunks_kb_id ON content_chunks(kb_id) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_content_chunks_doc_id ON content_chunks(doc_id) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_content_chunks_chunk_type ON content_chunks(chunk_type) WHERE deleted_at IS NULL")

    # ========== 8. search_vector trigger（自动维护 tsvector） ==========
    op.execute("""
    CREATE TRIGGER content_chunks_search_vector_trigger
        BEFORE INSERT OR UPDATE ON content_chunks
        FOR EACH ROW EXECUTE FUNCTION
        tsvector_update_trigger(search_vector, 'public.chinese_zh', text)
    """)

    # ========== 9. 空表预留（P2+） ==========
    op.execute("""
    CREATE TABLE organizations (
        id          SERIAL PRIMARY KEY,
        tenant_id   INT NOT NULL REFERENCES tenants(id),
        name        VARCHAR(200) NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at  TIMESTAMPTZ
    )
    """)
    op.execute("CREATE INDEX ix_organizations_tenant_id ON organizations(tenant_id) WHERE deleted_at IS NULL")

    op.execute("""
    CREATE TABLE org_members (
        id          SERIAL PRIMARY KEY,
        org_id      INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        user_id     INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role        VARCHAR(50) NOT NULL DEFAULT 'member',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at  TIMESTAMPTZ
    )
    """)
    op.execute("CREATE INDEX ix_org_members_org_id ON org_members(org_id) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_org_members_user_id ON org_members(user_id) WHERE deleted_at IS NULL")

    op.execute("""
    CREATE TABLE kb_shares (
        id          SERIAL PRIMARY KEY,
        kb_id       INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
        org_id      INT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
        permission  VARCHAR(50) NOT NULL DEFAULT 'read',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at  TIMESTAMPTZ
    )
    """)
    op.execute("CREATE INDEX ix_kb_shares_kb_id ON kb_shares(kb_id) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_kb_shares_org_id ON kb_shares(org_id) WHERE deleted_at IS NULL")

    op.execute("""
    CREATE TABLE llm_providers (
        id          SERIAL PRIMARY KEY,
        name        VARCHAR(100) NOT NULL,
        api_base    VARCHAR(500) NOT NULL DEFAULT '',
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at  TIMESTAMPTZ
    )
    """)

    op.execute("""
    CREATE TABLE user_llm_keys (
        id              SERIAL PRIMARY KEY,
        user_id         INT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        provider_id     INT NOT NULL REFERENCES llm_providers(id) ON DELETE CASCADE,
        encrypted_key   VARCHAR(1000) NOT NULL,
        created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at      TIMESTAMPTZ
    )
    """)
    op.execute("CREATE INDEX ix_user_llm_keys_user_id ON user_llm_keys(user_id) WHERE deleted_at IS NULL")

    op.execute("""
    CREATE TABLE wiki_folders (
        id                  SERIAL PRIMARY KEY,
        kb_id               INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
        parent_id           INT NOT NULL DEFAULT 0,
        name                VARCHAR(255) NOT NULL,
        materialized_path   VARCHAR(1000) NOT NULL DEFAULT '/',
        created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at          TIMESTAMPTZ
    )
    """)
    op.execute("CREATE INDEX ix_wiki_folders_kb_id ON wiki_folders(kb_id) WHERE deleted_at IS NULL")

    op.execute("""
    CREATE TABLE wiki_pages (
        id          SERIAL PRIMARY KEY,
        kb_id       INT NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
        folder_id   INT NOT NULL DEFAULT 0,
        page_type   VARCHAR(50) NOT NULL,
        title       VARCHAR(500) NOT NULL,
        content     TEXT NOT NULL,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        deleted_at  TIMESTAMPTZ
    )
    """)
    op.execute("CREATE INDEX ix_wiki_pages_kb_id ON wiki_pages(kb_id) WHERE deleted_at IS NULL")
    op.execute("CREATE INDEX ix_wiki_pages_page_type ON wiki_pages(page_type) WHERE deleted_at IS NULL")

    # 补回 content_chunks.wiki_page_id 的外键
    op.execute("""
    ALTER TABLE content_chunks
        ADD CONSTRAINT content_chunks_wiki_page_id_fkey
        FOREIGN KEY (wiki_page_id) REFERENCES wiki_pages(id) ON DELETE CASCADE
    """)


def downgrade() -> None:
    """回滚：按反序 DROP"""
    op.execute("ALTER TABLE content_chunks DROP CONSTRAINT IF EXISTS content_chunks_wiki_page_id_fkey")
    for table in [
        "wiki_pages",
        "wiki_folders",
        "user_llm_keys",
        "llm_providers",
        "kb_shares",
        "org_members",
        "organizations",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    op.execute("DROP TRIGGER IF EXISTS content_chunks_search_vector_trigger ON content_chunks")
    op.execute("DROP INDEX IF EXISTS content_chunks_embedding_1024_hnsw")
    op.execute("DROP INDEX IF EXISTS content_chunks_search_vector_gin")
    op.execute("DROP TABLE IF EXISTS content_chunks CASCADE")
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TABLE IF EXISTS sources CASCADE")
    op.execute("DROP TABLE IF EXISTS knowledge_bases CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS tenants CASCADE")

    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS chinese_zh")
    # 注意：不 DROP EXTENSION，避免影响其他 DB
