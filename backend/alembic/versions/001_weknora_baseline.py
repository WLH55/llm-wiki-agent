"""WeKnora 表结构全量基线（53 张表）

Revision ID: 001
Revises: None
Create Date: 2026-08-20

设计依据：
- mydocs/database-tables-catalog.md（WeKnora migrations/versioned 79 个迁移的最终结构解析）
- docs/adr/0001-adopt-weknora-schema.md（全量采用决策）
- mydocs/specs/2026-08-20_16-24_知识库表结构重设计.md（Spec §4 Plan 第三版）

本迁移推倒旧 23 张表与旧迁移链（原 001~004 已删除），单文件重建 WeKnora 全部 53 张表。

本地化（仅 3 处，其余逐字段照搬 catalog）：
1. UUID 默认值用 PG16 内建 gen_random_uuid()::text（WeKnora 原文 uuid_generate_v4() 依赖 uuid-ossp）
2. embeddings 向量/全文索引用本项目已验证参数：
   halfvec cosine HNSW(m=16, ef_construction=64) 按维度 partial；BM25 chinese_lindera 分词
3. 注释中文化（表级 + 语义不直观的列；catalog 列描述为中文，直接沿用）

兼容性：upgrade 开头幂等 DROP 新旧全部表名（IF EXISTS ... CASCADE），旧开发库/空库均可执行。
注意：旧库 alembic_version 指向已删除的 004，需先重置数据库（DROP SCHEMA public CASCADE 后重建）。
"""
from collections.abc import Sequence

from alembic import op

revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 旧项目 23 张表（含与 WeKnora 重名者，重名表由统一 DROP 覆盖）
_LEGACY_TABLES = [
    "task_outbox",
    "processing_spans",
    "processing_runs",
    "search_logs",
    "wiki_page_evidence_refs",
    "wiki_page_document_refs",
    "wiki_page_links",
    "kb_wiki_configs",
    "kb_rag_configs",
    "content_chunks",
    "document_revisions",
    "documents",
    "sources",
    "user_llm_keys",
    "llm_providers",
    "org_members",
]

# WeKnora 53 张表（依赖序：被引用者在前；downgrade 按此表逆序 DROP）
WEKNORA_TABLES = [
    "tenants", "users", "auth_tokens", "tenant_members", "tenant_invitations",
    "tenant_api_keys", "system_settings", "audit_logs",
    "models",
    "vector_stores", "storage_backends",
    "knowledge_bases", "knowledge_tags", "knowledges", "chunks", "chunk_revisions",
    "embeddings", "knowledge_tag_relations", "temporary_documents",
    "sessions", "messages", "message_suggestion_sets", "message_suggestion_events",
    "custom_agents", "mcp_services", "mcp_tool_approvals", "mcp_oauth_clients",
    "mcp_oauth_tokens", "web_search_providers",
    "im_channels", "im_channel_sessions", "embed_channels",
    "organizations", "organization_members", "organization_tenant_members",
    "organization_join_requests", "kb_shares", "agent_shares",
    "tenant_disabled_shared_agents",
    "wiki_folders", "wiki_pages", "wiki_page_revisions", "wiki_page_issues",
    "data_sources", "sync_logs",
    "resources", "resource_bindings", "resource_access_grants",
    "task_pending_ops", "task_dead_letters", "knowledge_processing_spans",
    "user_resource_favorites", "user_kb_pins",
]



def _exec(sql: str) -> None:
    """按分号拆分多语句 DDL 串逐条执行（asyncpg 预编译语句不支持多命令）。

    本迁移 DDL 不含函数体/触发器，字符串字面量中也不含分号，按 ';' 拆分安全；
    纯注释片段（去掉 -- 行后为空）跳过。
    """
    for stmt in sql.split(";"):
        body = "\n".join(
            line for line in stmt.splitlines() if not line.strip().startswith("--")
        )
        if body.strip():
            op.execute(stmt.strip())


def upgrade() -> None:
    """升级：推倒旧表，全量创建 WeKnora 53 张表。"""

    # ----- 0. 幂等清理：DROP 旧表与可能残留的新表 -----
    for table in _LEGACY_TABLES + WEKNORA_TABLES:
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')

    # ----- 0.1 扩展（与 postgres/init-extensions.sql 一致，幂等） -----
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_search")

    # ===== [域1: 租户/用户/认证/权限] =====
    _exec(
        """
        -- 租户：多租户核心，配额与全局配置
        CREATE TABLE tenants (
            id                        SERIAL PRIMARY KEY,
            name                      VARCHAR(255) NOT NULL,
            description               TEXT,
            retriever_engines         JSONB NOT NULL DEFAULT '[]'::jsonb,
            status                    VARCHAR(50) DEFAULT 'active',
            business                  VARCHAR(255) NOT NULL,
            storage_quota             BIGINT NOT NULL DEFAULT 10737418240,
            storage_used              BIGINT NOT NULL DEFAULT 0,
            agent_config              JSONB DEFAULT NULL,
            created_at                TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at                TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at                TIMESTAMP WITH TIME ZONE,
            context_config            JSONB,
            conversation_config       JSONB,
            web_search_config         JSONB DEFAULT NULL,
            parser_engine_config      JSONB DEFAULT NULL,
            storage_engine_config     JSONB DEFAULT NULL,
            chat_history_config       JSONB,
            retrieval_config          JSONB,
            credentials               JSONB DEFAULT NULL,
            api_principal_config      JSONB,
            default_storage_backend_id VARCHAR(36)
        );
        COMMENT ON TABLE tenants IS '系统多租户核心：配额、全局 Agent/检索/存储配置';
        CREATE INDEX idx_tenants_status ON tenants (status);

        -- 用户：可跨租户，is_system_admin 为平台级管理员
        CREATE TABLE users (
            id                     VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            username               VARCHAR(100) NOT NULL UNIQUE,
            email                  VARCHAR(255) NOT NULL UNIQUE,
            password_hash          VARCHAR(255) NOT NULL,
            avatar                 VARCHAR(500),
            tenant_id              INTEGER CONSTRAINT fk_users_tenant REFERENCES tenants (id) ON DELETE SET NULL,
            is_active              BOOLEAN NOT NULL DEFAULT TRUE,
            created_at             TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at             TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at             TIMESTAMP WITH TIME ZONE,
            can_access_all_tenants BOOLEAN NOT NULL DEFAULT FALSE,
            preferences            JSONB NOT NULL DEFAULT '{}'::jsonb,
            is_system_admin        BOOLEAN NOT NULL DEFAULT FALSE
        );
        COMMENT ON TABLE users IS '用户账户，可跨租户（can_access_all_tenants），is_system_admin 为平台级管理员';
        COMMENT ON COLUMN users.preferences IS '用户偏好 JSON（记忆开关等 UI 配置）';
        CREATE INDEX idx_users_tenant_id ON users (tenant_id);
        CREATE INDEX idx_users_deleted_at ON users (deleted_at);
        CREATE INDEX idx_users_is_system_admin ON users (is_system_admin);

        -- 登录令牌（access/refresh），支持撤销
        CREATE TABLE auth_tokens (
            id          VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            user_id     VARCHAR(36) NOT NULL CONSTRAINT fk_auth_tokens_user REFERENCES users (id) ON DELETE CASCADE,
            token       TEXT NOT NULL,
            token_type  VARCHAR(50) NOT NULL,
            expires_at  TIMESTAMP WITH TIME ZONE NOT NULL,
            is_revoked  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        COMMENT ON TABLE auth_tokens IS '登录令牌（access_token/refresh_token），支持撤销';
        CREATE INDEX idx_auth_tokens_user_id ON auth_tokens (user_id);
        CREATE INDEX idx_auth_tokens_token ON auth_tokens (token);
        CREATE INDEX idx_auth_tokens_token_type ON auth_tokens (token_type);
        CREATE INDEX idx_auth_tokens_expires_at ON auth_tokens (expires_at);

        -- 租户成员与角色（RBAC）
        CREATE TABLE tenant_members (
            id         BIGSERIAL PRIMARY KEY,
            user_id    VARCHAR(36) NOT NULL,
            tenant_id  INTEGER NOT NULL,
            role       VARCHAR(20) NOT NULL DEFAULT 'contributor',
            status     VARCHAR(20) NOT NULL DEFAULT 'active',
            invited_by VARCHAR(36),
            joined_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE tenant_members IS '租户内成员与角色（owner/admin/contributor/viewer）';
        CREATE UNIQUE INDEX idx_tenant_members_user_tenant_unique ON tenant_members (user_id, tenant_id);
        CREATE INDEX idx_tenant_members_tenant_role ON tenant_members (tenant_id, role);
        CREATE INDEX idx_tenant_members_user ON tenant_members (user_id);

        -- 租户邀请（定向邀请 + 分享链接）
        CREATE TABLE tenant_invitations (
            id              BIGSERIAL PRIMARY KEY,
            tenant_id       INTEGER NOT NULL,
            invitee_user_id VARCHAR(36) NOT NULL,
            invited_by      VARCHAR(36),
            role            VARCHAR(20) NOT NULL,
            status          VARCHAR(20) NOT NULL DEFAULT 'pending',
            message         VARCHAR(500),
            expires_at      TIMESTAMP WITH TIME ZONE NOT NULL,
            responded_at    TIMESTAMP WITH TIME ZONE,
            created_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at      TIMESTAMP WITH TIME ZONE,
            token           VARCHAR(64) NOT NULL DEFAULT '',
            accepted_count  INTEGER NOT NULL DEFAULT 0
        );
        COMMENT ON TABLE tenant_invitations IS '租户邀请（定向邀请 + 分享链接两种模式）';
        COMMENT ON COLUMN tenant_invitations.token IS '分享链接注册令牌（明文，短 TTL）';
        COMMENT ON COLUMN tenant_invitations.accepted_count IS '通过该邀请完成注册的人数（分享链接累积）';
        CREATE UNIQUE INDEX idx_tenant_invitations_unique_pending
            ON tenant_invitations (tenant_id, invitee_user_id)
            WHERE status = 'pending' AND invitee_user_id <> '';
        CREATE INDEX idx_tenant_invitations_tenant ON tenant_invitations (tenant_id);
        CREATE INDEX idx_tenant_invitations_invitee ON tenant_invitations (invitee_user_id);
        CREATE INDEX idx_tenant_invitations_token ON tenant_invitations (token) WHERE token <> '';

        -- 租户/平台级 API Key（哈希 + 白名单 + 能力授权）
        CREATE TABLE tenant_api_keys (
            id                  BIGSERIAL PRIMARY KEY,
            tenant_id           INTEGER NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            name                VARCHAR(128) NOT NULL,
            key_hash            VARCHAR(64) NOT NULL UNIQUE,
            api_key             TEXT NOT NULL DEFAULT '',
            full_access         BOOLEAN NOT NULL DEFAULT FALSE,
            knowledge_base_ids  JSONB NOT NULL DEFAULT '[]'::jsonb,
            capabilities        JSONB NOT NULL DEFAULT '[]'::jsonb,
            last_used_at        TIMESTAMP WITH TIME ZONE,
            expires_at          TIMESTAMP WITH TIME ZONE,
            revoked_at          TIMESTAMP WITH TIME ZONE,
            created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            scope_type          VARCHAR(16) NOT NULL DEFAULT 'tenant',
            CONSTRAINT chk_tenant_api_keys_scope CHECK (
                (scope_type = 'tenant' AND tenant_id IS NOT NULL)
                OR (scope_type = 'platform' AND tenant_id IS NULL AND full_access = FALSE)
            )
        );
        COMMENT ON TABLE tenant_api_keys IS '租户/平台级 API Key 管理（哈希存储 + 知识库白名单 + 能力授权）';
        COMMENT ON COLUMN tenant_api_keys.api_key IS '原始 Key（应用层加密存储）';
        CREATE INDEX idx_tenant_api_keys_tenant ON tenant_api_keys (tenant_id);
        CREATE INDEX idx_tenant_api_keys_revoked_at ON tenant_api_keys (revoked_at);
        CREATE INDEX idx_tenant_api_keys_scope_type ON tenant_api_keys (scope_type);

        -- 平台级设置（键值 JSONB），仅系统管理员可改
        CREATE TABLE system_settings (
            id               BIGSERIAL PRIMARY KEY,
            key              VARCHAR(128) NOT NULL UNIQUE,
            value            JSONB NOT NULL,
            value_type       VARCHAR(16) NOT NULL,
            category         VARCHAR(32) NOT NULL,
            description      TEXT NOT NULL DEFAULT '',
            is_secret        BOOLEAN NOT NULL DEFAULT FALSE,
            requires_restart BOOLEAN NOT NULL DEFAULT FALSE,
            last_modified_by VARCHAR(36) NOT NULL DEFAULT '',
            created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        COMMENT ON TABLE system_settings IS '平台级设置（键值 JSONB），仅系统管理员可改';
        CREATE INDEX idx_system_settings_category ON system_settings (category);

        -- 操作审计
        CREATE TABLE audit_logs (
            id             BIGSERIAL PRIMARY KEY,
            tenant_id      BIGINT NOT NULL,
            actor_user_id  VARCHAR(36) NOT NULL DEFAULT '',
            actor_role     VARCHAR(32) NOT NULL DEFAULT '',
            action         VARCHAR(64) NOT NULL,
            target_type    VARCHAR(32) NOT NULL DEFAULT '',
            target_id      VARCHAR(64) NOT NULL DEFAULT '',
            target_user_id VARCHAR(36) NOT NULL DEFAULT '',
            request_path   VARCHAR(512) NOT NULL DEFAULT '',
            request_method VARCHAR(16) NOT NULL DEFAULT '',
            outcome        VARCHAR(16) NOT NULL DEFAULT 'success',
            details        JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            scope_type     VARCHAR(32) NOT NULL DEFAULT '',
            scope_id       VARCHAR(64) NOT NULL DEFAULT ''
        );
        COMMENT ON TABLE audit_logs IS '操作审计（谁在何时对什么目标做了什么，含请求路径）';
        CREATE INDEX idx_audit_logs_tenant_id_desc ON audit_logs (tenant_id, id DESC);
        CREATE INDEX idx_audit_logs_actor ON audit_logs (actor_user_id);
        CREATE INDEX idx_audit_logs_tenant_action ON audit_logs (tenant_id, action);
        CREATE INDEX idx_audit_logs_created_at ON audit_logs (created_at);
        CREATE INDEX idx_audit_logs_tenant_scope_desc ON audit_logs (tenant_id, scope_type, scope_id, id DESC);
        """
    )

    # ===== [域2: 模型配置] =====
    _exec(
        """
        -- 模型注册中心：type 决定用途（KnowledgeQA/Embedding/Rerank 等），tenant_id=0 为系统内置
        CREATE TABLE models (
            id          VARCHAR(64) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id   INTEGER NOT NULL,
            name        VARCHAR(255) NOT NULL,
            display_name VARCHAR(255) NOT NULL DEFAULT '',
            type        VARCHAR(50) NOT NULL,
            source      VARCHAR(50) NOT NULL,
            description TEXT,
            parameters  JSONB NOT NULL,
            is_default  BOOLEAN NOT NULL DEFAULT FALSE,
            status      VARCHAR(50) NOT NULL DEFAULT 'active',
            created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at  TIMESTAMP WITH TIME ZONE,
            is_builtin  BOOLEAN NOT NULL DEFAULT FALSE,
            managed_by  VARCHAR(32) NOT NULL DEFAULT ''
        );
        COMMENT ON TABLE models IS '模型注册中心：type 决定用途，tenant_id=0 表示系统内置模型';
        COMMENT ON COLUMN models.parameters IS '模型参数 JSONB（base_url、api_key 等）';
        CREATE INDEX idx_models_type ON models (type);
        CREATE INDEX idx_models_source ON models (source);
        CREATE INDEX idx_models_is_builtin ON models (is_builtin);
        CREATE INDEX idx_models_managed_by_yaml ON models (managed_by);
        """
    )

    # ===== [域3: 向量库注册 + 存储后端（被 knowledge_bases 逻辑引用）] =====
    _exec(
        """
        -- 外部向量库注册（pgvector/ES/Milvus 等），知识库可选绑定
        CREATE TABLE vector_stores (
            id                VARCHAR(36) NOT NULL PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name              VARCHAR(255) NOT NULL,
            engine_type       VARCHAR(50) NOT NULL,
            connection_config JSONB NOT NULL DEFAULT '{}'::jsonb,
            index_config      JSONB NOT NULL DEFAULT '{}'::jsonb,
            tenant_id         BIGINT NOT NULL,
            created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at        TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE vector_stores IS '外部向量库注册（pgvector/elasticsearch/milvus 等），知识库可选绑定';
        CREATE INDEX idx_vector_stores_name_tenant ON vector_stores (name, tenant_id);
        CREATE INDEX idx_vector_stores_tenant_id ON vector_stores (tenant_id);
        CREATE INDEX idx_vector_stores_engine_type ON vector_stores (engine_type);
        CREATE INDEX idx_vector_stores_deleted_at ON vector_stores (deleted_at);

        -- 统一存储后端注册（local/minio/cos），供文档与资源使用
        CREATE TABLE storage_backends (
            id            VARCHAR(36) NOT NULL PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id     BIGINT NOT NULL,
            name          VARCHAR(255) NOT NULL,
            provider      VARCHAR(32) NOT NULL,
            config        JSONB NOT NULL DEFAULT '{}'::jsonb,
            source        VARCHAR(16) NOT NULL DEFAULT 'user',
            status        VARCHAR(16) NOT NULL DEFAULT 'active',
            legacy_alias  BOOLEAN NOT NULL DEFAULT FALSE,
            created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at    TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE storage_backends IS '统一存储后端注册（local/minio/cos），供文档与资源使用';
        CREATE INDEX idx_storage_backends_name_tenant ON storage_backends (tenant_id, name);
        CREATE INDEX idx_storage_backends_legacy_alias ON storage_backends (tenant_id, provider);
        CREATE INDEX idx_storage_backends_tenant ON storage_backends (tenant_id);
        """
    )

    # ===== [域4: 知识库 / 文档 / 切块 / 向量] =====
    _exec(
        """
        -- 知识库容器：继承租户级模型/存储配置，可覆盖；type 区分 document/faq
        CREATE TABLE knowledge_bases (
            id                      VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name                    VARCHAR(255) NOT NULL,
            description             TEXT,
            tenant_id               INTEGER NOT NULL,
            embedding_model_id      VARCHAR(64) NOT NULL,
            summary_model_id        VARCHAR(64) NOT NULL,
            cos_config              JSONB NOT NULL DEFAULT '{}',
            vlm_config              JSONB NOT NULL DEFAULT '{}',
            extract_config          JSONB DEFAULT NULL,
            created_at              TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at              TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at              TIMESTAMP WITH TIME ZONE,
            is_temporary            BOOLEAN NOT NULL DEFAULT FALSE,
            type                    VARCHAR(32) NOT NULL DEFAULT 'document',
            faq_config              JSONB,
            question_generation_config JSONB DEFAULT NULL,
            storage_provider_config JSONB DEFAULT NULL,
            is_pinned               BOOLEAN NOT NULL DEFAULT FALSE,
            pinned_at               TIMESTAMP WITH TIME ZONE,
            asr_config              JSONB,
            vector_store_id         VARCHAR(36),
            wiki_config             JSONB,
            indexing_strategy       JSONB,
            creator_id              VARCHAR(36),
            storage_backend_id      VARCHAR(36)
        );
        COMMENT ON TABLE knowledge_bases IS '知识库容器：继承租户级模型/存储配置，可覆盖；type 区分 document/faq';
        COMMENT ON COLUMN knowledge_bases.indexing_strategy IS '索引策略：{"vector_enabled","keyword_enabled","wiki_enabled","graph_enabled"}';
        COMMENT ON COLUMN knowledge_bases.wiki_config IS 'Wiki 配置：{"auto_ingest","synthesis_model_id","wiki_language","max_pages_per_ingest"}';
        CREATE INDEX idx_knowledge_bases_tenant_id ON knowledge_bases (tenant_id);
        CREATE INDEX idx_knowledge_bases_tenant_vector_store ON knowledge_bases (tenant_id, vector_store_id);
        CREATE INDEX idx_knowledge_bases_tenant_creator ON knowledge_bases (tenant_id, creator_id);
        CREATE INDEX idx_knowledge_bases_storage_backend ON knowledge_bases (tenant_id, storage_backend_id);

        -- 知识库内标签（FAQ 分类与过滤）
        CREATE TABLE knowledge_tags (
            id                VARCHAR(36) PRIMARY KEY,
            tenant_id         INTEGER NOT NULL,
            knowledge_base_id VARCHAR(36) NOT NULL,
            name              VARCHAR(128) NOT NULL,
            color             VARCHAR(32),
            sort_order        INTEGER NOT NULL DEFAULT 0,
            created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at        TIMESTAMP WITH TIME ZONE,
            seq_id            BIGINT
        );
        COMMENT ON TABLE knowledge_tags IS '知识库内标签，用于 FAQ 分类与过滤';
        CREATE UNIQUE INDEX idx_knowledge_tags_kb_name ON knowledge_tags (tenant_id, knowledge_base_id, name) WHERE deleted_at IS NULL;
        CREATE INDEX idx_knowledge_tags_kb ON knowledge_tags (tenant_id, knowledge_base_id);
        CREATE UNIQUE INDEX idx_knowledge_tags_seq_id ON knowledge_tags (seq_id) WHERE seq_id IS NOT NULL;

        -- 知识条目：文档/FAQ，parse_status 生命周期 unprocessed→processing→finalizing→completed
        CREATE TABLE knowledges (
            id                     VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id              INTEGER NOT NULL,
            knowledge_base_id      VARCHAR(36) NOT NULL,
            type                   VARCHAR(50) NOT NULL,
            title                  VARCHAR(255) NOT NULL,
            description            TEXT,
            source                 VARCHAR(2048) NOT NULL,
            parse_status           VARCHAR(50) NOT NULL DEFAULT 'unprocessed',
            enable_status          VARCHAR(50) NOT NULL DEFAULT 'enabled',
            embedding_model_id     VARCHAR(64),
            file_name              VARCHAR(255),
            file_type              VARCHAR(50),
            file_size              BIGINT,
            file_path              TEXT,
            file_hash              VARCHAR(64),
            storage_size           BIGINT NOT NULL DEFAULT 0,
            metadata               JSONB,
            created_at             TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at             TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            processed_at           TIMESTAMP WITH TIME ZONE,
            error_message          TEXT,
            deleted_at             TIMESTAMP WITH TIME ZONE,
            summary_status         VARCHAR(32) DEFAULT 'none',
            last_faq_import_result JSON DEFAULT NULL,
            channel                VARCHAR(50) NOT NULL DEFAULT 'web',
            pending_subtasks_count INT NOT NULL DEFAULT 0,
            custom_metadata        JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        COMMENT ON TABLE knowledges IS '知识库内的文档/FAQ 条目；parse_status: unprocessed/processing/finalizing/completed/failed';
        COMMENT ON COLUMN knowledges.enable_status IS '启用状态：enabled/disabled';
        COMMENT ON COLUMN knowledges.channel IS '来源渠道：web/api/browser_extension/wechat 等';
        COMMENT ON COLUMN knowledges.pending_subtasks_count IS '未完成的富化子任务数（parse_status=finalizing 时 >0）';
        CREATE INDEX idx_knowledges_tenant_id ON knowledges (tenant_id);
        CREATE INDEX idx_knowledges_base_id ON knowledges (knowledge_base_id);
        CREATE INDEX idx_knowledges_parse_status ON knowledges (parse_status);
        CREATE INDEX idx_knowledges_enable_status ON knowledges (enable_status);
        CREATE INDEX idx_knowledges_summary_status ON knowledges (summary_status);
        CREATE INDEX idx_knowledges_kb_metadata_external_id ON knowledges (knowledge_base_id, (metadata ->> 'external_id'));

        -- 知识切块：文本/表格/图像，父子层级与前后链，seq_id 供外部 API 使用
        CREATE TABLE chunks (
            id                      VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id               INTEGER NOT NULL,
            knowledge_base_id       VARCHAR(36) NOT NULL,
            knowledge_id            VARCHAR(36) NOT NULL,
            content                 TEXT NOT NULL,
            chunk_index             INTEGER NOT NULL,
            is_enabled              BOOLEAN NOT NULL DEFAULT TRUE,
            start_at                INTEGER NOT NULL,
            end_at                  INTEGER NOT NULL,
            pre_chunk_id            VARCHAR(36),
            next_chunk_id           VARCHAR(36),
            chunk_type              VARCHAR(20) NOT NULL DEFAULT 'text',
            parent_chunk_id         VARCHAR(36),
            image_info              TEXT,
            relation_chunks         JSONB,
            indirect_relation_chunks JSONB,
            created_at              TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at              TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at              TIMESTAMP WITH TIME ZONE,
            metadata                JSONB,
            tag_id                  VARCHAR(36),
            status                  INT NOT NULL DEFAULT 0,
            content_hash            VARCHAR(64),
            flags                   INTEGER NOT NULL DEFAULT 1,
            seq_id                  BIGINT,
            video_info              TEXT,
            source_content          TEXT NOT NULL DEFAULT '',
            content_revision        INT NOT NULL DEFAULT 0,
            index_status            VARCHAR(16) NOT NULL DEFAULT 'ready',
            last_editor_id          VARCHAR(64) NOT NULL DEFAULT '',
            context_header          TEXT NOT NULL DEFAULT ''
        );
        COMMENT ON TABLE chunks IS '知识切块（text/table/image/faq），支持父子层级与前后链；可编辑并留修订';
        COMMENT ON COLUMN chunks.tag_id IS '标签 ID（knowledge_tags.id，弃用中）';
        COMMENT ON COLUMN chunks.flags IS '位标志（bit1=推荐等，默认 1）';
        COMMENT ON COLUMN chunks.seq_id IS '对外 API 使用的自增 ID';
        COMMENT ON COLUMN chunks.source_content IS '原始内容（未编辑的源文本）';
        COMMENT ON COLUMN chunks.content_revision IS '内容修订号（编辑历史）';
        COMMENT ON COLUMN chunks.index_status IS '索引状态：ready/pending/failed 等';
        CREATE INDEX idx_chunks_tenant_kg ON chunks (tenant_id, knowledge_id);
        CREATE INDEX idx_chunks_parent_id ON chunks (parent_chunk_id);
        CREATE INDEX idx_chunks_chunk_type ON chunks (chunk_type);
        CREATE INDEX idx_chunks_tag ON chunks (tag_id);
        CREATE INDEX idx_chunks_content_hash ON chunks (content_hash);
        CREATE UNIQUE INDEX idx_chunks_seq_id ON chunks (seq_id) WHERE seq_id IS NOT NULL;
        CREATE INDEX idx_chunks_kb_tenant ON chunks (knowledge_base_id, tenant_id);
        CREATE INDEX idx_chunks_knowledge_enabled ON chunks (knowledge_id, is_enabled) WHERE deleted_at IS NULL;

        -- 块编辑修订历史
        CREATE TABLE chunk_revisions (
            id                VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id         BIGINT NOT NULL,
            knowledge_base_id VARCHAR(36) NOT NULL,
            knowledge_id      VARCHAR(36) NOT NULL,
            chunk_id          VARCHAR(36) NOT NULL,
            revision          INT NOT NULL,
            content           TEXT NOT NULL DEFAULT '',
            is_enabled        BOOLEAN NOT NULL DEFAULT TRUE,
            editor_id         VARCHAR(64) NOT NULL DEFAULT '',
            edit_source       VARCHAR(16) NOT NULL DEFAULT 'user',
            edited_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        COMMENT ON TABLE chunk_revisions IS '块编辑修订历史（chunk 手动编辑后回溯）';
        CREATE INDEX idx_chunk_revisions_chunk_revision ON chunk_revisions (chunk_id, revision);
        CREATE INDEX idx_chunk_revisions_tenant_chunk ON chunk_revisions (tenant_id, chunk_id);

        -- 向量索引核心表：维度分区 HNSW + BM25 全文（pg_search）
        CREATE TABLE embeddings (
            id                SERIAL PRIMARY KEY,
            created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            source_id         VARCHAR(64) NOT NULL,
            source_type       INTEGER NOT NULL,
            chunk_id          VARCHAR(64),
            knowledge_id      VARCHAR(64),
            knowledge_base_id VARCHAR(64),
            content           TEXT,
            dimension         INTEGER NOT NULL,
            embedding         halfvec,
            is_enabled        BOOLEAN DEFAULT TRUE,
            tag_id            VARCHAR(36)
        );
        COMMENT ON TABLE embeddings IS '向量索引核心表：source 唯一，halfvec 半精度向量，content 供 BM25 检索';
        CREATE UNIQUE INDEX embeddings_unique_source ON embeddings (source_id, source_type);
        CREATE INDEX idx_embeddings_is_enabled ON embeddings (is_enabled);
        CREATE INDEX idx_embeddings_knowledge_base_id ON embeddings (knowledge_base_id);
        CREATE INDEX idx_embeddings_tag_id ON embeddings (tag_id);
        """
    )

    # 向量 HNSW（按维度 partial，本地化参数）+ BM25（chinese_lindera）
    # 新维度接入时按同样模式补一条 partial HNSW
    _exec(
        """
        CREATE INDEX embeddings_embedding_1024_hnsw
            ON embeddings USING hnsw ((embedding::halfvec(1024)) halfvec_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            WHERE dimension = 1024;
        CREATE INDEX embeddings_bm25_idx
            ON embeddings USING bm25 (id, knowledge_base_id, knowledge_id, chunk_id, content)
            WITH (key_field = 'id', text_fields = '{"content": {"tokenizer": {"type": "chinese_lindera"}}}');
        """
    )

    # ===== [域5: 标签关系 + 临时文档] =====
    _exec(
        """
        -- 知识条目-标签多对多关系（替代单值 tag_id）
        CREATE TABLE knowledge_tag_relations (
            knowledge_id VARCHAR(36) NOT NULL,
            tag_id       VARCHAR(36) NOT NULL,
            created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            PRIMARY KEY (knowledge_id, tag_id)
        );
        COMMENT ON TABLE knowledge_tag_relations IS '知识条目-标签多对多关系表';
        CREATE INDEX idx_ktr_knowledge ON knowledge_tag_relations (knowledge_id);
        CREATE INDEX idx_ktr_tag ON knowledge_tag_relations (tag_id);

        -- 会话中暂存的上传文档（处理后过期清理）
        CREATE TABLE temporary_documents (
            id                VARCHAR(36) NOT NULL PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id         BIGINT NOT NULL,
            session_id        VARCHAR(36) NOT NULL,
            resource_ref      TEXT NOT NULL,
            file_name         VARCHAR(1024) NOT NULL,
            file_type         VARCHAR(32) NOT NULL,
            mime_type         VARCHAR(255) NOT NULL DEFAULT '',
            file_size         BIGINT NOT NULL,
            status            VARCHAR(16) NOT NULL DEFAULT 'uploaded',
            content           TEXT NOT NULL DEFAULT '',
            chunks            JSONB NOT NULL DEFAULT '[]'::jsonb,
            image_refs        JSONB NOT NULL DEFAULT '[]'::jsonb,
            metadata          JSONB NOT NULL DEFAULT '{}'::jsonb,
            processing_options JSONB NOT NULL DEFAULT '{}'::jsonb,
            token_count       INTEGER NOT NULL DEFAULT 0,
            chunk_count       INTEGER NOT NULL DEFAULT 0,
            error_message     TEXT NOT NULL DEFAULT '',
            expires_at        TIMESTAMP WITH TIME ZONE NOT NULL,
            started_at        TIMESTAMP WITH TIME ZONE,
            ready_at          TIMESTAMP WITH TIME ZONE,
            created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at        TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE temporary_documents IS '会话中暂存的上传文档（uploaded/processing/ready/failed/expired，过期清理）';
        CREATE INDEX idx_temporary_documents_scope ON temporary_documents (tenant_id, session_id);
        CREATE INDEX idx_temporary_documents_status ON temporary_documents (status);
        CREATE INDEX idx_temporary_documents_expires ON temporary_documents (expires_at);
        """
    )

    # ===== [域6: 会话 / 消息 / 问答] =====
    _exec(
        """
        -- 问答会话：绑定知识库与 Agent，携带检索参数与兜底策略
        CREATE TABLE sessions (
            id                 VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id          INTEGER NOT NULL,
            title              VARCHAR(255),
            description        TEXT,
            knowledge_base_id  VARCHAR(36),
            max_rounds         INTEGER NOT NULL DEFAULT 5,
            enable_rewrite     BOOLEAN NOT NULL DEFAULT TRUE,
            fallback_strategy  VARCHAR(255) NOT NULL DEFAULT 'fixed',
            fallback_response  TEXT NOT NULL DEFAULT '很抱歉，我暂时无法回答这个问题。',
            keyword_threshold  FLOAT NOT NULL DEFAULT 0.5,
            vector_threshold   FLOAT NOT NULL DEFAULT 0.5,
            rerank_model_id    VARCHAR(64),
            embedding_top_k    INTEGER NOT NULL DEFAULT 10,
            rerank_top_k       INTEGER NOT NULL DEFAULT 10,
            rerank_threshold   FLOAT NOT NULL DEFAULT 0.65,
            summary_model_id   VARCHAR(64),
            summary_parameters JSONB NOT NULL DEFAULT '{}',
            agent_config       JSONB DEFAULT NULL,
            context_config     JSONB DEFAULT NULL,
            created_at         TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at         TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at         TIMESTAMP WITH TIME ZONE,
            agent_id           VARCHAR(36),
            user_id            VARCHAR(512),
            is_pinned          BOOLEAN NOT NULL DEFAULT FALSE,
            pinned_at          TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE sessions IS '问答会话：绑定知识库与 Agent，携带检索参数（阈值、top_k）与兜底策略';
        CREATE INDEX idx_sessions_tenant_id ON sessions (tenant_id);
        CREATE INDEX idx_sessions_agent_id ON sessions (agent_id);
        CREATE INDEX idx_sessions_tenant_user_pin
            ON sessions (tenant_id, user_id, is_pinned DESC, pinned_at DESC, updated_at DESC);

        -- 会话消息：含知识引用、Agent 步骤、渲染内容、附件
        CREATE TABLE messages (
            id                    VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            request_id            VARCHAR(36) NOT NULL,
            session_id            VARCHAR(36) NOT NULL,
            role                  VARCHAR(50) NOT NULL,
            content               TEXT NOT NULL,
            knowledge_references  JSONB NOT NULL DEFAULT '[]',
            agent_steps           JSONB DEFAULT NULL,
            is_completed          BOOLEAN NOT NULL DEFAULT FALSE,
            created_at            TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at            TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at            TIMESTAMP WITH TIME ZONE,
            mentioned_items       JSONB DEFAULT '[]',
            is_fallback           BOOLEAN DEFAULT FALSE,
            agent_duration_ms     BIGINT DEFAULT 0,
            knowledge_id          VARCHAR(36),
            images                JSONB DEFAULT '[]',
            channel               VARCHAR(50) NOT NULL DEFAULT '',
            rendered_content      TEXT NOT NULL DEFAULT '',
            attachments           JSONB DEFAULT '[]',
            agent_id              VARCHAR(36) NOT NULL DEFAULT '',
            agent_tenant_id       INTEGER NOT NULL DEFAULT 0,
            model_id              VARCHAR(64) NOT NULL DEFAULT '',
            execution_context     JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        COMMENT ON TABLE messages IS '会话消息：含知识引用、Agent 步骤、渲染内容、附件等';
        COMMENT ON COLUMN messages.rendered_content IS '完整 RAG 增强后的用户消息（跨轮保留检索上下文）';
        CREATE INDEX idx_messages_session_id ON messages (session_id);
        CREATE INDEX idx_messages_knowledge_id ON messages (knowledge_id);
        CREATE INDEX idx_messages_agent_id ON messages (agent_id);

        -- 助手消息的推荐问题缓存（去重键 config_hash+placement+locale）
        CREATE TABLE message_suggestion_sets (
            id                   VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id            INTEGER NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            session_id           VARCHAR(36) NOT NULL,
            assistant_message_id VARCHAR(36) NOT NULL,
            agent_id             VARCHAR(36) NOT NULL DEFAULT '',
            agent_tenant_id      INTEGER NOT NULL DEFAULT 0,
            placement            VARCHAR(32) NOT NULL,
            config_hash          VARCHAR(64) NOT NULL,
            locale               VARCHAR(16) NOT NULL DEFAULT '',
            status               VARCHAR(16) NOT NULL,
            allow_regenerate     BOOLEAN NOT NULL DEFAULT FALSE,
            suppression_reason   VARCHAR(64) NOT NULL DEFAULT '',
            questions            JSONB NOT NULL DEFAULT '[]'::jsonb,
            model_id             VARCHAR(64) NOT NULL DEFAULT '',
            prompt_tokens        INTEGER NOT NULL DEFAULT 0,
            completion_tokens    INTEGER NOT NULL DEFAULT 0,
            latency_ms           BIGINT NOT NULL DEFAULT 0,
            error_code           VARCHAR(64) NOT NULL DEFAULT '',
            lease_until          TIMESTAMP WITH TIME ZONE,
            generated_at         TIMESTAMP WITH TIME ZONE,
            created_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        COMMENT ON TABLE message_suggestion_sets IS '助手消息的推荐问题缓存（去重键 config_hash+placement+locale）';
        CREATE INDEX idx_message_suggestion_sets_cache_key
            ON message_suggestion_sets (tenant_id, assistant_message_id, placement, config_hash, locale);
        CREATE INDEX idx_message_suggestion_sets_session
            ON message_suggestion_sets (tenant_id, session_id, created_at DESC);
        CREATE INDEX idx_message_suggestion_sets_status ON message_suggestion_sets (status, lease_until);

        -- 推荐问题点击/展示埋点事件
        CREATE TABLE message_suggestion_events (
            id                BIGSERIAL PRIMARY KEY,
            tenant_id         INTEGER NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            session_id        VARCHAR(36) NOT NULL,
            suggestion_set_id VARCHAR(36) NOT NULL REFERENCES message_suggestion_sets (id) ON DELETE CASCADE,
            question_id       VARCHAR(64) NOT NULL DEFAULT '',
            event_type        VARCHAR(32) NOT NULL,
            actor_id          VARCHAR(512) NOT NULL DEFAULT '',
            created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        COMMENT ON TABLE message_suggestion_events IS '推荐问题点击/展示埋点事件';
        CREATE INDEX idx_message_suggestion_events_set ON message_suggestion_events (suggestion_set_id, created_at);
        CREATE INDEX idx_message_suggestion_events_session
            ON message_suggestion_events (tenant_id, session_id, created_at);
        CREATE INDEX idx_message_suggestion_events_type ON message_suggestion_events (event_type, created_at);
        """
    )

    # ===== [域7: Agent / MCP / Web 搜索] =====
    _exec(
        """
        -- 自定义 Agent（GPTs 式）：复合主键 (id, tenant_id) 允许同 id 多租户内置 Agent
        CREATE TABLE custom_agents (
            id                VARCHAR(36) NOT NULL DEFAULT gen_random_uuid()::text,
            name              VARCHAR(255) NOT NULL,
            description       TEXT,
            avatar            VARCHAR(64),
            is_builtin        BOOLEAN NOT NULL DEFAULT FALSE,
            tenant_id         INTEGER NOT NULL,
            created_by        VARCHAR(36),
            config            JSONB NOT NULL DEFAULT '{}',
            created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at        TIMESTAMP WITH TIME ZONE,
            runnable_by_viewer BOOLEAN NOT NULL DEFAULT TRUE,
            PRIMARY KEY (id, tenant_id)
        );
        COMMENT ON TABLE custom_agents IS '自定义 Agent（GPTs 式），config JSONB 保存完整配置';
        COMMENT ON COLUMN custom_agents.config IS 'Agent 配置（agent_mode、system_prompt、模型、工具、检索参数等）';
        CREATE INDEX idx_custom_agents_tenant_id ON custom_agents (tenant_id);
        CREATE INDEX idx_custom_agents_is_builtin ON custom_agents (is_builtin);
        CREATE INDEX idx_custom_agents_deleted_at ON custom_agents (deleted_at);

        -- MCP 服务注册（SSE/HTTP/stdio 传输）
        CREATE TABLE mcp_services (
            id             VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id      INTEGER NOT NULL,
            name           VARCHAR(255) NOT NULL,
            description    TEXT,
            enabled        BOOLEAN DEFAULT TRUE,
            transport_type VARCHAR(50) NOT NULL,
            url            VARCHAR(512),
            headers        JSONB,
            auth_config    JSONB,
            advanced_config JSONB,
            stdio_config   JSONB,
            env_vars       JSONB,
            created_at     TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at     TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at     TIMESTAMP WITH TIME ZONE,
            is_builtin     BOOLEAN NOT NULL DEFAULT FALSE
        );
        COMMENT ON TABLE mcp_services IS 'MCP 服务注册（sse/streamable-http/stdio 传输），支持认证与内置服务';
        CREATE INDEX idx_mcp_services_tenant_id ON mcp_services (tenant_id);
        CREATE INDEX idx_mcp_services_enabled ON mcp_services (enabled);
        CREATE INDEX idx_mcp_services_deleted_at ON mcp_services (deleted_at);
        CREATE INDEX idx_mcp_services_is_builtin ON mcp_services (is_builtin);

        -- MCP 工具级审批开关
        CREATE TABLE mcp_tool_approvals (
            id               VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id        INTEGER NOT NULL,
            service_id       VARCHAR(36) NOT NULL REFERENCES mcp_services (id) ON DELETE CASCADE,
            tool_name        VARCHAR(512) NOT NULL,
            require_approval BOOLEAN NOT NULL DEFAULT FALSE,
            created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        COMMENT ON TABLE mcp_tool_approvals IS 'MCP 工具级审批开关';
        CREATE INDEX idx_mcp_tool_approvals_tenant_svc_tool
            ON mcp_tool_approvals (tenant_id, service_id, tool_name);
        CREATE INDEX idx_mcp_tool_approvals_service_id ON mcp_tool_approvals (service_id);

        -- MCP OAuth 客户端注册
        CREATE TABLE mcp_oauth_clients (
            id            VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id     INTEGER NOT NULL,
            service_id    VARCHAR(36) NOT NULL REFERENCES mcp_services (id) ON DELETE CASCADE,
            client_id     VARCHAR(512) NOT NULL,
            client_secret TEXT,
            redirect_uri  VARCHAR(1024),
            created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        COMMENT ON TABLE mcp_oauth_clients IS 'MCP OAuth 客户端注册';
        CREATE INDEX idx_mcp_oauth_clients_tenant_svc ON mcp_oauth_clients (tenant_id, service_id);
        CREATE INDEX idx_mcp_oauth_clients_service_id ON mcp_oauth_clients (service_id);

        -- MCP OAuth 用户授权令牌（principal 模型，刷新租约防并发）
        CREATE TABLE mcp_oauth_tokens (
            id                  VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id           INTEGER NOT NULL,
            user_id             VARCHAR(512) NOT NULL,
            service_id          VARCHAR(36) NOT NULL REFERENCES mcp_services (id) ON DELETE CASCADE,
            access_token        TEXT,
            refresh_token       TEXT,
            token_type          VARCHAR(32),
            expires_at          TIMESTAMP WITH TIME ZONE,
            created_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            principal_type      VARCHAR(32),
            principal_id        VARCHAR(512),
            refresh_lease_id    VARCHAR(36),
            refresh_lease_until TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE mcp_oauth_tokens IS 'MCP OAuth 用户授权令牌（principal 身份模型 + 刷新租约防并发）';
        CREATE INDEX idx_mcp_oauth_tokens_tenant_user_svc
            ON mcp_oauth_tokens (tenant_id, user_id, service_id);
        CREATE INDEX idx_mcp_oauth_tokens_service_id ON mcp_oauth_tokens (service_id);
        CREATE INDEX idx_mcp_oauth_tokens_user_id ON mcp_oauth_tokens (user_id);
        CREATE UNIQUE INDEX idx_mcp_oauth_tokens_tenant_principal_svc
            ON mcp_oauth_tokens (tenant_id, principal_type, principal_id, service_id)
            WHERE principal_type IS NOT NULL AND principal_id IS NOT NULL;
        CREATE INDEX idx_mcp_oauth_tokens_principal ON mcp_oauth_tokens (principal_type, principal_id);

        -- Web 搜索提供商配置
        CREATE TABLE web_search_providers (
            id          VARCHAR(36) NOT NULL PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id   BIGINT NOT NULL,
            name        VARCHAR(255) NOT NULL,
            provider    VARCHAR(50) NOT NULL,
            description TEXT,
            parameters  JSONB,
            is_default  BOOLEAN DEFAULT FALSE,
            created_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at  TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE web_search_providers IS 'Web 搜索提供商配置（bing/serper/tavily 等）';
        CREATE INDEX idx_web_search_providers_tenant_id ON web_search_providers (tenant_id);
        CREATE INDEX idx_web_search_providers_provider ON web_search_providers (provider);
        CREATE INDEX idx_web_search_providers_deleted_at ON web_search_providers (deleted_at);
        """
    )

    # ===== [域8: IM 接入 / 嵌入渠道] =====
    _exec(
        """
        -- IM 渠道配置（平台凭据、绑定 Agent/KB）
        CREATE TABLE im_channels (
            id                VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id         BIGINT NOT NULL,
            agent_id          VARCHAR(36) NOT NULL,
            platform          VARCHAR(20) NOT NULL,
            name              VARCHAR(255) NOT NULL DEFAULT '',
            enabled           BOOLEAN NOT NULL DEFAULT TRUE,
            mode              VARCHAR(20) NOT NULL DEFAULT 'websocket',
            output_mode       VARCHAR(20) NOT NULL DEFAULT 'stream',
            credentials       JSONB NOT NULL DEFAULT '{}',
            created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at        TIMESTAMP WITH TIME ZONE,
            knowledge_base_id VARCHAR(36) DEFAULT '',
            bot_identity      VARCHAR(255) NOT NULL DEFAULT '',
            session_mode      VARCHAR(20) NOT NULL DEFAULT 'user',
            CONSTRAINT chk_im_channels_session_mode CHECK (session_mode IN ('user', 'thread'))
        );
        COMMENT ON TABLE im_channels IS 'IM 渠道配置（企微/钉钉/飞书等：凭据、绑定 Agent/KB）';
        COMMENT ON COLUMN im_channels.bot_identity IS '机器人身份标识（防重复绑定，如 wecom:ws:{bot_id}）';
        CREATE INDEX idx_im_channels_tenant ON im_channels (tenant_id);
        CREATE INDEX idx_im_channels_agent ON im_channels (agent_id);
        CREATE INDEX idx_im_channels_deleted ON im_channels (deleted_at);
        CREATE INDEX idx_im_channels_bot_identity ON im_channels (bot_identity);

        -- IM 平台会话 ↔ 内部 session 映射
        CREATE TABLE im_channel_sessions (
            id             VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            platform       VARCHAR(20) NOT NULL,
            user_id        VARCHAR(128) NOT NULL,
            chat_id        VARCHAR(128) NOT NULL DEFAULT '',
            session_id     VARCHAR(36) NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
            tenant_id      BIGINT NOT NULL,
            agent_id       VARCHAR(36) DEFAULT '',
            status         VARCHAR(20) NOT NULL DEFAULT 'active',
            metadata       JSONB DEFAULT '{}',
            created_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at     TIMESTAMP WITH TIME ZONE,
            im_channel_id  VARCHAR(36) DEFAULT '',
            thread_id      VARCHAR(128) NOT NULL DEFAULT ''
        );
        COMMENT ON TABLE im_channel_sessions IS 'IM 平台会话与内部 session 的映射（thread 模式支持群聊线程）';
        CREATE INDEX idx_channel_lookup ON im_channel_sessions (platform, user_id, chat_id, tenant_id, agent_id);
        CREATE INDEX idx_channel_thread_lookup
            ON im_channel_sessions (platform, chat_id, thread_id, tenant_id, agent_id);
        CREATE INDEX idx_im_channel_tenant ON im_channel_sessions (tenant_id);
        CREATE INDEX idx_im_channel_session ON im_channel_sessions (session_id);
        CREATE INDEX idx_im_channel_deleted ON im_channel_sessions (deleted_at);
        CREATE INDEX idx_im_channel_sessions_channel ON im_channel_sessions (im_channel_id);

        -- 公开嵌入渠道（网页挂件：发布令牌 + 限流 + 主题定制）
        CREATE TABLE embed_channels (
            id                        VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id                 BIGINT NOT NULL,
            agent_id                  VARCHAR(36) NOT NULL DEFAULT 'builtin-quick-answer',
            name                      VARCHAR(255) NOT NULL DEFAULT '',
            enabled                   BOOLEAN NOT NULL DEFAULT TRUE,
            publish_token             VARCHAR(64) NOT NULL DEFAULT '',
            allowed_origins           JSONB NOT NULL DEFAULT '[]',
            welcome_message           TEXT NOT NULL DEFAULT '',
            rate_limit_per_minute     INTEGER NOT NULL DEFAULT 30,
            rate_limit_per_day        INTEGER NOT NULL DEFAULT 10000,
            primary_color             VARCHAR(32) NOT NULL DEFAULT '',
            page_title                VARCHAR(255) NOT NULL DEFAULT '',
            header_title_mode         VARCHAR(32) NOT NULL DEFAULT 'channel',
            show_suggested_questions  BOOLEAN NOT NULL DEFAULT TRUE,
            widget_position           VARCHAR(32) NOT NULL DEFAULT 'bottom-right',
            allow_web_search          BOOLEAN NOT NULL DEFAULT FALSE,
            allow_memory              BOOLEAN NOT NULL DEFAULT FALSE,
            allow_file_upload         BOOLEAN NOT NULL DEFAULT FALSE,
            default_locale            VARCHAR(16) NOT NULL DEFAULT '',
            webhook_url               VARCHAR(512) NOT NULL DEFAULT '',
            webhook_secret            VARCHAR(128) NOT NULL DEFAULT '',
            created_at                TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at                TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at                TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE embed_channels IS '公开嵌入渠道（iframe 挂件：发布令牌、CORS 白名单、限流、主题）';
        CREATE INDEX idx_embed_channels_tenant ON embed_channels (tenant_id);
        CREATE INDEX idx_embed_channels_agent ON embed_channels (agent_id);
        CREATE INDEX idx_embed_channels_publish_token ON embed_channels (publish_token);
        CREATE INDEX idx_embed_channels_deleted_at ON embed_channels (deleted_at);
        """
    )

    # ===== [域9: 组织协作 / 内容分享] =====
    _exec(
        """
        -- 跨租户协作空间（共享空间），邀请码/审批加入
        CREATE TABLE organizations (
            id                        VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            name                      VARCHAR(255) NOT NULL,
            description               TEXT,
            owner_id                  VARCHAR(36) NOT NULL,
            invite_code               VARCHAR(32),
            require_approval          BOOLEAN DEFAULT FALSE,
            invite_code_expires_at    TIMESTAMP WITH TIME ZONE,
            invite_code_validity_days SMALLINT NOT NULL DEFAULT 7,
            avatar                    VARCHAR(512) DEFAULT '',
            searchable                BOOLEAN NOT NULL DEFAULT FALSE,
            member_limit              INTEGER NOT NULL DEFAULT 50,
            created_at                TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at                TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at                TIMESTAMP WITH TIME ZONE,
            owner_tenant_id           BIGINT
        );
        COMMENT ON TABLE organizations IS '跨租户协作空间（共享空间），通过邀请码/审批加入';
        CREATE UNIQUE INDEX idx_organizations_invite_code
            ON organizations (invite_code) WHERE deleted_at IS NULL AND invite_code IS NOT NULL AND invite_code <> '';
        CREATE INDEX idx_organizations_owner_id ON organizations (owner_id);
        CREATE INDEX idx_organizations_deleted_at ON organizations (deleted_at);
        CREATE INDEX idx_organizations_owner_tenant ON organizations (owner_tenant_id);

        -- 组织成员（用户粒度）与角色
        CREATE TABLE organization_members (
            id              VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            organization_id VARCHAR(36) NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
            user_id         VARCHAR(36) NOT NULL,
            tenant_id       INTEGER NOT NULL,
            role            VARCHAR(32) NOT NULL DEFAULT 'viewer',
            created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        COMMENT ON TABLE organization_members IS '组织成员（用户粒度）与角色：admin/editor/viewer';
        CREATE UNIQUE INDEX idx_org_members_org_user ON organization_members (organization_id, user_id);
        CREATE INDEX idx_org_members_user_id ON organization_members (user_id);
        CREATE INDEX idx_org_members_tenant_id ON organization_members (tenant_id);
        CREATE INDEX idx_org_members_role ON organization_members (role);

        -- 组织-租户粒度成员关系（跨租户协作）
        CREATE TABLE organization_tenant_members (
            id                    VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            organization_id       VARCHAR(36) NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
            tenant_id             INTEGER NOT NULL,
            role                  VARCHAR(32) NOT NULL DEFAULT 'viewer',
            representative_user_id VARCHAR(36) NOT NULL DEFAULT '',
            joined_at             TIMESTAMP WITH TIME ZONE,
            created_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at            TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        COMMENT ON TABLE organization_tenant_members IS '组织-租户粒度成员关系（租户而非用户作为组织成员）';
        CREATE UNIQUE INDEX idx_org_tenant_members_unique ON organization_tenant_members (organization_id, tenant_id);
        CREATE INDEX idx_org_tenant_members_by_tenant ON organization_tenant_members (tenant_id);
        CREATE INDEX idx_org_tenant_members_role ON organization_tenant_members (organization_id, role);

        -- 加入/升级角色的审批流
        CREATE TABLE organization_join_requests (
            id              VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            organization_id VARCHAR(36) NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
            user_id         VARCHAR(36) NOT NULL,
            tenant_id       INTEGER NOT NULL,
            status          VARCHAR(32) NOT NULL DEFAULT 'pending',
            requested_role  VARCHAR(32) NOT NULL DEFAULT 'viewer',
            request_type    VARCHAR(32) NOT NULL DEFAULT 'join',
            prev_role       VARCHAR(32),
            message         TEXT,
            reviewed_by     VARCHAR(36),
            reviewed_at     TIMESTAMP WITH TIME ZONE,
            review_message  TEXT,
            created_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        COMMENT ON TABLE organization_join_requests IS '加入/升级角色的审批流（request_type: join/upgrade）';
        CREATE INDEX idx_org_join_requests_org_user_pending
            ON organization_join_requests (organization_id, user_id) WHERE status = 'pending';
        CREATE INDEX idx_org_join_requests_org_id ON organization_join_requests (organization_id);
        CREATE INDEX idx_org_join_requests_user_id ON organization_join_requests (user_id);
        CREATE INDEX idx_org_join_requests_status ON organization_join_requests (status);
        CREATE INDEX idx_org_join_requests_type ON organization_join_requests (request_type);
        CREATE UNIQUE INDEX uq_org_join_requests_pending_per_tenant
            ON organization_join_requests (organization_id, tenant_id, request_type) WHERE status = 'pending';

        -- 知识库→组织分享（跨租户访问，source_tenant_id 记录源）
        CREATE TABLE kb_shares (
            id                 VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            knowledge_base_id  VARCHAR(36) NOT NULL REFERENCES knowledge_bases (id) ON DELETE CASCADE,
            organization_id    VARCHAR(36) NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
            shared_by_user_id  VARCHAR(36) NOT NULL,
            source_tenant_id   INTEGER NOT NULL,
            permission         VARCHAR(32) NOT NULL DEFAULT 'viewer',
            created_at         TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at         TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at         TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE kb_shares IS '知识库→组织分享，跨租户访问（source_tenant_id 记录源）';
        CREATE UNIQUE INDEX idx_kb_shares_kb_org
            ON kb_shares (knowledge_base_id, organization_id) WHERE deleted_at IS NULL;
        CREATE INDEX idx_kb_shares_kb_id ON kb_shares (knowledge_base_id);
        CREATE INDEX idx_kb_shares_org_id ON kb_shares (organization_id);
        CREATE INDEX idx_kb_shares_source_tenant ON kb_shares (source_tenant_id);
        CREATE INDEX idx_kb_shares_deleted_at ON kb_shares (deleted_at);

        -- 自定义 Agent→组织分享（复合外键指向 custom_agents(id, tenant_id)）
        CREATE TABLE agent_shares (
            id                 VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            agent_id           VARCHAR(36) NOT NULL,
            organization_id    VARCHAR(36) NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
            shared_by_user_id  VARCHAR(36) NOT NULL,
            source_tenant_id   INTEGER NOT NULL,
            permission         VARCHAR(32) NOT NULL DEFAULT 'viewer',
            created_at         TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at         TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at         TIMESTAMP WITH TIME ZONE,
            FOREIGN KEY (agent_id, source_tenant_id)
                REFERENCES custom_agents (id, tenant_id) ON DELETE CASCADE
        );
        COMMENT ON TABLE agent_shares IS '自定义 Agent→组织分享';
        CREATE UNIQUE INDEX idx_agent_shares_agent_org
            ON agent_shares (agent_id, source_tenant_id, organization_id) WHERE deleted_at IS NULL;
        CREATE INDEX idx_agent_shares_agent_id ON agent_shares (agent_id);
        CREATE INDEX idx_agent_shares_org_id ON agent_shares (organization_id);
        CREATE INDEX idx_agent_shares_source_tenant ON agent_shares (source_tenant_id);
        CREATE INDEX idx_agent_shares_deleted_at ON agent_shares (deleted_at);

        -- 租户级禁用共享 Agent 名单
        CREATE TABLE tenant_disabled_shared_agents (
            tenant_id         BIGINT NOT NULL,
            agent_id          VARCHAR(36) NOT NULL,
            source_tenant_id  BIGINT NOT NULL,
            created_at        TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, agent_id, source_tenant_id)
        );
        COMMENT ON TABLE tenant_disabled_shared_agents IS '租户级禁用共享 Agent 名单';
        CREATE INDEX idx_tenant_disabled_shared_agents_tenant_id ON tenant_disabled_shared_agents (tenant_id);
        """
    )

    # ===== [域10: Wiki 知识整理] =====
    _exec(
        """
        -- Wiki 目录树（邻接表），页面 folder_id 归属
        CREATE TABLE wiki_folders (
            id                VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id         BIGINT NOT NULL DEFAULT 0,
            knowledge_base_id VARCHAR(36) NOT NULL,
            parent_id         VARCHAR(36) NOT NULL DEFAULT '',
            name              VARCHAR(255) NOT NULL,
            path              VARCHAR(1024) NOT NULL DEFAULT '',
            depth             INT NOT NULL DEFAULT 0,
            sort_order        INT NOT NULL DEFAULT 0,
            created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            deleted_at        TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE wiki_folders IS 'Wiki 目录树（邻接表），path 为物化路径';
        CREATE INDEX idx_wiki_folders_parent_name ON wiki_folders (knowledge_base_id, parent_id, name);
        CREATE INDEX idx_wiki_folders_parent ON wiki_folders (knowledge_base_id, parent_id);
        CREATE INDEX idx_wiki_folders_deleted_at ON wiki_folders (deleted_at);

        -- Wiki 页面：目录归属、双向链接、来源引用（JSONB），多页面类型
        CREATE TABLE wiki_pages (
            id                VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id         BIGINT NOT NULL,
            knowledge_base_id VARCHAR(36) NOT NULL,
            slug              VARCHAR(255) NOT NULL,
            title             VARCHAR(512) NOT NULL DEFAULT '',
            page_type         VARCHAR(32) NOT NULL DEFAULT 'summary',
            status            VARCHAR(32) NOT NULL DEFAULT 'published',
            content           TEXT NOT NULL DEFAULT '',
            summary           TEXT NOT NULL DEFAULT '',
            parent_slug       VARCHAR(255) NOT NULL DEFAULT '',
            folder_id         VARCHAR(36) NOT NULL DEFAULT '',
            category_path     JSONB DEFAULT '[]',
            wiki_path         VARCHAR(1024) NOT NULL DEFAULT '',
            depth             INT NOT NULL DEFAULT 0,
            sort_order        INT NOT NULL DEFAULT 0,
            source_refs       JSONB DEFAULT '[]',
            chunk_refs        JSONB DEFAULT '[]',
            in_links          JSONB DEFAULT '[]',
            out_links         JSONB DEFAULT '[]',
            page_metadata     JSONB DEFAULT '{}',
            aliases           JSONB DEFAULT '[]',
            version           INT NOT NULL DEFAULT 1,
            created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            deleted_at        TIMESTAMP WITH TIME ZONE,
            last_edit_source  VARCHAR(16) NOT NULL DEFAULT '',
            last_editor_id    VARCHAR(64) NOT NULL DEFAULT ''
        );
        COMMENT ON TABLE wiki_pages IS 'Wiki 页面（知识整理产物）：目录归属、双向链接、来源引用（JSONB）';
        COMMENT ON COLUMN wiki_pages.in_links IS '入链页面列表（JSONB）';
        COMMENT ON COLUMN wiki_pages.out_links IS '出链页面列表（JSONB）';
        COMMENT ON COLUMN wiki_pages.source_refs IS '来源引用（JSONB）';
        COMMENT ON COLUMN wiki_pages.chunk_refs IS '引用块（JSONB）';
        CREATE UNIQUE INDEX idx_wiki_pages_kb_slug ON wiki_pages (knowledge_base_id, slug) WHERE deleted_at IS NULL;
        CREATE INDEX idx_wiki_pages_kb_id ON wiki_pages (knowledge_base_id);
        CREATE INDEX idx_wiki_pages_page_type ON wiki_pages (knowledge_base_id, page_type);
        CREATE INDEX idx_wiki_pages_parent_slug ON wiki_pages (knowledge_base_id, parent_slug);
        CREATE INDEX idx_wiki_pages_tree ON wiki_pages (knowledge_base_id, page_type, wiki_path, sort_order, title);
        CREATE INDEX idx_wiki_pages_folder ON wiki_pages (knowledge_base_id, folder_id);
        CREATE INDEX idx_wiki_pages_tenant_id ON wiki_pages (tenant_id);
        CREATE INDEX idx_wiki_pages_deleted_at ON wiki_pages (deleted_at);
        CREATE INDEX idx_wiki_pages_folder_id ON wiki_pages (folder_id);

        -- Wiki 页面版本历史
        CREATE TABLE wiki_page_revisions (
            id                VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id         BIGINT NOT NULL,
            knowledge_base_id VARCHAR(36) NOT NULL,
            page_id           VARCHAR(36) NOT NULL,
            slug              VARCHAR(255) NOT NULL,
            version           INT NOT NULL,
            title             VARCHAR(512) NOT NULL DEFAULT '',
            page_type         VARCHAR(32) NOT NULL DEFAULT 'summary',
            status            VARCHAR(32) NOT NULL DEFAULT 'published',
            content           TEXT NOT NULL DEFAULT '',
            summary           TEXT NOT NULL DEFAULT '',
            aliases           JSONB DEFAULT '[]',
            edit_source       VARCHAR(16) NOT NULL DEFAULT '',
            editor_id         VARCHAR(64) NOT NULL DEFAULT '',
            edited_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            created_at        TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        COMMENT ON TABLE wiki_page_revisions IS 'Wiki 页面版本历史';
        CREATE INDEX idx_wiki_page_revisions_page_version ON wiki_page_revisions (page_id, version);
        CREATE INDEX idx_wiki_page_revisions_kb_slug ON wiki_page_revisions (knowledge_base_id, slug);

        -- Wiki 页面质量问题上报
        CREATE TABLE wiki_page_issues (
            id                     VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id              BIGINT NOT NULL,
            knowledge_base_id      VARCHAR(36) NOT NULL,
            slug                   VARCHAR(255) NOT NULL,
            issue_type             VARCHAR(50) NOT NULL,
            description            TEXT NOT NULL,
            suspected_knowledge_ids JSONB,
            status                 VARCHAR(20) NOT NULL DEFAULT 'pending',
            reported_by            VARCHAR(100) NOT NULL,
            created_at             TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at             TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at             TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE wiki_page_issues IS 'Wiki 页面质量问题上报（content-error/missing-info 等）';
        CREATE INDEX idx_wiki_page_issues_tenant_id ON wiki_page_issues (tenant_id);
        CREATE INDEX idx_wiki_page_issues_knowledge_base_id ON wiki_page_issues (knowledge_base_id);
        CREATE INDEX idx_wiki_page_issues_slug ON wiki_page_issues (slug);
        CREATE INDEX idx_wiki_page_issues_status ON wiki_page_issues (status);
        """
    )

    # ===== [域11: 数据源同步 + 存储与资源 + 任务队列 + 用户个性化] =====
    _exec(
        """
        -- 外部数据源（webhook/api/db）定时同步到知识库
        CREATE TABLE data_sources (
            id                       VARCHAR(36) NOT NULL PRIMARY KEY DEFAULT gen_random_uuid()::text,
            tenant_id                BIGINT NOT NULL,
            knowledge_base_id        VARCHAR(36) NOT NULL,
            name                     VARCHAR(255) NOT NULL,
            type                     VARCHAR(50) NOT NULL,
            config                   JSONB,
            sync_schedule            VARCHAR(100),
            sync_mode                VARCHAR(20) DEFAULT 'incremental',
            status                   VARCHAR(32) DEFAULT 'active',
            conflict_strategy        VARCHAR(32) DEFAULT 'overwrite',
            sync_deletions           BOOLEAN DEFAULT TRUE,
            last_sync_at             TIMESTAMP WITH TIME ZONE,
            last_sync_cursor         JSONB,
            last_sync_result         JSONB,
            error_message            TEXT,
            sync_log_retention_days  INT DEFAULT 30,
            created_at               TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at               TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at               TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE data_sources IS '外部数据源（webhook/api/database/file）定时同步到知识库';
        CREATE INDEX idx_data_sources_tenant_id ON data_sources (tenant_id);
        CREATE INDEX idx_data_sources_knowledge_base_id ON data_sources (knowledge_base_id);
        CREATE INDEX idx_data_sources_type ON data_sources (type);
        CREATE INDEX idx_data_sources_status ON data_sources (status);
        CREATE INDEX idx_data_sources_deleted_at ON data_sources (deleted_at);

        -- 数据源同步执行日志与统计
        CREATE TABLE sync_logs (
            id               VARCHAR(36) NOT NULL PRIMARY KEY DEFAULT gen_random_uuid()::text,
            data_source_id   VARCHAR(36) NOT NULL REFERENCES data_sources (id) ON DELETE CASCADE,
            tenant_id        BIGINT NOT NULL,
            status           VARCHAR(32) NOT NULL,
            started_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            finished_at      TIMESTAMP WITH TIME ZONE,
            items_total      INT DEFAULT 0,
            items_created    INT DEFAULT 0,
            items_updated    INT DEFAULT 0,
            items_deleted    INT DEFAULT 0,
            items_skipped    INT DEFAULT 0,
            items_failed     INT DEFAULT 0,
            error_message    TEXT,
            result           JSONB,
            created_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at       TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        COMMENT ON TABLE sync_logs IS '数据源同步执行日志与统计';
        CREATE INDEX idx_sync_logs_data_source_id ON sync_logs (data_source_id);
        CREATE INDEX idx_sync_logs_tenant_id ON sync_logs (tenant_id);
        CREATE INDEX idx_sync_logs_status ON sync_logs (status);
        CREATE INDEX idx_sync_logs_started_at ON sync_logs (started_at);

        -- 对象资源注册表：handle 短链接标识，多生命周期
        CREATE TABLE resources (
            id                  VARCHAR(36) NOT NULL PRIMARY KEY DEFAULT gen_random_uuid()::text,
            handle              VARCHAR(22) NOT NULL UNIQUE,
            tenant_id           BIGINT NOT NULL,
            storage_backend_id  VARCHAR(36),
            provider            VARCHAR(32) NOT NULL,
            physical_path       TEXT NOT NULL,
            location_hash       VARCHAR(64) NOT NULL,
            kind                VARCHAR(32) NOT NULL DEFAULT 'file',
            mime_type           VARCHAR(255) NOT NULL DEFAULT '',
            original_name       VARCHAR(1024) NOT NULL DEFAULT '',
            size                BIGINT NOT NULL DEFAULT 0,
            content_hash        VARCHAR(64) NOT NULL DEFAULT '',
            lifecycle           VARCHAR(16) NOT NULL DEFAULT 'persistent',
            expires_at          TIMESTAMP WITH TIME ZONE,
            state               VARCHAR(16) NOT NULL DEFAULT 'active',
            created_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
            deleted_at          TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE resources IS '对象资源注册表（文件/图像），handle 短句柄唯一，多生命周期';
        CREATE INDEX idx_resources_tenant_location ON resources (tenant_id, location_hash);
        CREATE INDEX idx_resources_tenant ON resources (tenant_id);
        CREATE INDEX idx_resources_backend ON resources (storage_backend_id);

        -- 资源与业务实体（知识/会话/消息）的绑定关系
        CREATE TABLE resource_bindings (
            id           VARCHAR(36) NOT NULL PRIMARY KEY DEFAULT gen_random_uuid()::text,
            resource_id  VARCHAR(36) NOT NULL REFERENCES resources (id) ON DELETE CASCADE,
            tenant_id    BIGINT NOT NULL,
            owner_type   VARCHAR(32) NOT NULL,
            owner_id     VARCHAR(64) NOT NULL,
            relation     VARCHAR(32) NOT NULL DEFAULT 'attachment',
            created_at   TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        COMMENT ON TABLE resource_bindings IS '资源与业务实体（knowledge/session/message 等）的绑定关系';
        CREATE UNIQUE INDEX idx_resource_bindings_unique
            ON resource_bindings (resource_id, owner_type, owner_id, relation);
        CREATE INDEX idx_resource_bindings_owner ON resource_bindings (tenant_id, owner_type, owner_id);

        -- 资源限时访问令牌授权（分享链接）
        CREATE TABLE resource_access_grants (
            id            VARCHAR(36) NOT NULL PRIMARY KEY DEFAULT gen_random_uuid()::text,
            token_hash    VARCHAR(64) NOT NULL UNIQUE,
            resource_id   VARCHAR(36) NOT NULL REFERENCES resources (id) ON DELETE CASCADE,
            access_scope  VARCHAR(16) NOT NULL DEFAULT 'read',
            expires_at    TIMESTAMP WITH TIME ZONE NOT NULL,
            revoked_at    TIMESTAMP WITH TIME ZONE,
            created_at    TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );
        COMMENT ON TABLE resource_access_grants IS '资源限时访问令牌授权（分享链接）';
        CREATE INDEX idx_resource_access_grants_resource ON resource_access_grants (resource_id);
        CREATE INDEX idx_resource_access_grants_expires ON resource_access_grants (expires_at);

        -- 去重任务队列（wiki 批量摄取等），支持认领与失败计数
        CREATE TABLE task_pending_ops (
            id           BIGSERIAL PRIMARY KEY,
            tenant_id    BIGINT NOT NULL,
            task_type    VARCHAR(64) NOT NULL,
            scope        VARCHAR(32) NOT NULL,
            scope_id     VARCHAR(64) NOT NULL,
            op           VARCHAR(32) NOT NULL,
            dedup_key    VARCHAR(128) NOT NULL DEFAULT '',
            payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
            fail_count   INT NOT NULL DEFAULT 0,
            enqueued_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            claimed_at   TIMESTAMP WITH TIME ZONE
        );
        COMMENT ON TABLE task_pending_ops IS '通用持久化去重任务队列（task_type+scope+scope_id 定位；claimed_at 过期可恢复）';
        CREATE INDEX idx_task_pending_ops_scope ON task_pending_ops (task_type, scope, scope_id, id);
        CREATE INDEX idx_task_pending_ops_tenant ON task_pending_ops (tenant_id);

        -- 任务死信：重试耗尽的任务载荷永久留存
        CREATE TABLE task_dead_letters (
            id           BIGSERIAL PRIMARY KEY,
            tenant_id    BIGINT NOT NULL,
            task_type    VARCHAR(64) NOT NULL,
            scope        VARCHAR(32) NOT NULL,
            scope_id     VARCHAR(64) NOT NULL,
            related_id   VARCHAR(64) NOT NULL DEFAULT '',
            payload      JSONB NOT NULL,
            last_error   TEXT NOT NULL DEFAULT '',
            fail_count   INT NOT NULL,
            failed_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        );
        COMMENT ON TABLE task_dead_letters IS '重试耗尽任务的永久归档（payload 留存，可 SQL 手动重放）';
        CREATE INDEX idx_task_dead_letters_scope ON task_dead_letters (scope, scope_id, failed_at DESC);
        CREATE INDEX idx_task_dead_letters_tenant ON task_dead_letters (tenant_id, failed_at DESC);
        CREATE INDEX idx_task_dead_letters_task_type ON task_dead_letters (task_type, failed_at DESC);

        -- 文档处理链路追踪（跨度树：根→阶段→子跨度→生成）
        CREATE TABLE knowledge_processing_spans (
            id             BIGSERIAL PRIMARY KEY,
            knowledge_id   VARCHAR(64) NOT NULL,
            attempt        INT NOT NULL DEFAULT 1,
            span_id        VARCHAR(64) NOT NULL,
            parent_span_id VARCHAR(64),
            name           VARCHAR(255) NOT NULL,
            kind           VARCHAR(16) NOT NULL,
            status         VARCHAR(16) NOT NULL,
            input          JSONB,
            output         JSONB,
            metadata       JSONB,
            error_code     VARCHAR(64),
            error_message  TEXT,
            error_detail   TEXT,
            started_at     TIMESTAMP WITH TIME ZONE,
            finished_at    TIMESTAMP WITH TIME ZONE,
            duration_ms    BIGINT,
            created_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_kpspan_attempt_span UNIQUE (knowledge_id, attempt, span_id)
        );
        COMMENT ON TABLE knowledge_processing_spans IS '文档处理链路追踪（kind: root/stage/subspan/generation）';
        CREATE INDEX idx_kpspan_knowledge_attempt ON knowledge_processing_spans (knowledge_id, attempt);
        CREATE INDEX idx_kpspan_status_started ON knowledge_processing_spans (status, started_at);
        CREATE INDEX idx_kpspan_parent ON knowledge_processing_spans (parent_span_id);

        -- 用户收藏（知识库/Agent）
        CREATE TABLE user_resource_favorites (
            user_id       VARCHAR(36) NOT NULL,
            tenant_id     BIGINT NOT NULL,
            resource_type VARCHAR(16) NOT NULL,
            resource_id   VARCHAR(64) NOT NULL,
            created_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, tenant_id, resource_type, resource_id)
        );
        COMMENT ON TABLE user_resource_favorites IS '用户收藏（资源类型：kb/agent）';
        CREATE INDEX idx_user_resource_favorites_user_tenant_type_created_at
            ON user_resource_favorites (user_id, tenant_id, resource_type, created_at DESC);
        CREATE INDEX idx_user_resource_favorites_tenant_id ON user_resource_favorites (tenant_id);

        -- 用户级知识库置顶
        CREATE TABLE user_kb_pins (
            tenant_id  BIGINT NOT NULL,
            user_id    VARCHAR(36) NOT NULL,
            kb_id      VARCHAR(36) NOT NULL,
            pinned_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, user_id, kb_id)
        );
        COMMENT ON TABLE user_kb_pins IS '用户级知识库置顶';
        CREATE INDEX idx_user_kb_pins_user_tenant_pinned_at ON user_kb_pins (tenant_id, user_id, pinned_at DESC);
        """
    )


def downgrade() -> None:
    """降级：按依赖逆序 DROP 全部 53 张表（不恢复旧表）。"""
    for table in reversed(WEKNORA_TABLES):
        op.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
