# WeKnora 数据库表结构文档（分类目录）

> 来源：项目 `migrations/versioned/` 下 79 个 PostgreSQL 版本化迁移脚本（000000_init ~ 000078）逐条合并、解析而得，反映**最新最终表结构**。
> 当前共 **53 张表**（另有 1 张已废弃删除的表：`wiki_log_entries`）。
> ⚠️ **本文档适用于你的部署**：当前运行的数据库是 **ParadeDB（PostgreSQL 17 内核的兼容分支）**，它直接执行 `migrations/versioned/` 这套 PostgreSQL 迁移，53 张表的定义与本文档**完全一致**。
> MySQL / SQLite 脚本只是同一套表结构的方言翻译/遗留精简版（详见下文「各数据库驱动的表结构关系」），对当前部署无实际作用，可忽略。

## 表总览（按分类）

| 分类 | 表 |
|---|---|
| 租户 / 用户 / 认证 / 权限 | `tenants`, `users`, `auth_tokens`, `tenant_members`, `tenant_invitations`, `tenant_api_keys`, `system_settings`, `audit_logs` |
| 模型配置 | `models` |
| 知识库 / 文档 / 切块 / 向量 | `knowledge_bases`, `knowledges`, `chunks`, `chunk_revisions`, `embeddings`, `knowledge_tags`, `knowledge_tag_relations`, `temporary_documents`, `vector_stores` |
| 会话 / 消息 / 问答 | `sessions`, `messages`, `message_suggestion_sets`, `message_suggestion_events` |
| Agent / MCP | `custom_agents`, `mcp_services`, `mcp_tool_approvals`, `mcp_oauth_clients`, `mcp_oauth_tokens`, `web_search_providers` |
| IM 接入 / 嵌入渠道 | `im_channel_sessions`, `im_channels`, `embed_channels` |
| 组织协作 / 内容分享 | `organizations`, `organization_members`, `organization_tenant_members`, `organization_join_requests`, `kb_shares`, `agent_shares`, `tenant_disabled_shared_agents` |
| Wiki 知识整理 | `wiki_pages`, `wiki_folders`, `wiki_page_issues`, `wiki_page_revisions` |
| 数据源同步 | `data_sources`, `sync_logs` |
| 存储与资源 | `storage_backends`, `resources`, `resource_bindings`, `resource_access_grants` |
| 任务队列 / 处理追踪 | `task_pending_ops`, `task_dead_letters`, `knowledge_processing_spans` |
| 用户个性化 | `user_resource_favorites`, `user_kb_pins` |


---


---

## 各数据库驱动的表结构关系（MySQL / SQLite 与 PostgreSQL 是什么关系？）

**一句话：它们是同一套业务表结构，只是分别用不同数据库的 SQL 方言写的。** 不是三套不同的设计。

| 驱动 | 脚本位置 | 表数量 | 性质 | 谁在用 |
|---|---|---|---|---|
| **PostgreSQL / ParadeDB** | `migrations/versioned/`（79 个迁移） | **53** | ✅ **唯一权威主版本**（master schema），功能最全 | 标准部署 & 本机当前部署（ParadeDB pg17） |
| SQLite（Lite 模式） | `migrations/sqlite/`（000000_init + 000001） | 46 | 从 PostgreSQL 迁移**手工合并翻译**成 SQLite 方言，供轻量单机模式 | `DB_DRIVER=sqlite`（WeKnora Lite，见 `.env.lite`） |
| MySQL | `migrations/mysql/00-init-db.sql`（单文件） | 10 | **遗留的最小引导脚本**，未与 79 个迁移同步维护 | ⚠️ 代码中主库并不支持（见下） |

**具体关系：**

- **PostgreSQL 版是源头（source of truth）**。79 个版本化迁移（000000~000078）逐步建出全部 53 张表；ParadeDB 是 PostgreSQL 的兼容分支（v0.22.2-pg17 即 PG17 内核），**原样执行同一套迁移**，所以表和字段与本文档完全一致。
- **SQLite 版 = 同一套表的方言翻译**。`sqlite/000000_init.up.sql` 文件头就写着 *"SQLite schema for WeKnora Lite (consolidated from all Postgres migrations)"*——把 JSONB→TEXT、TIMESTAMPTZ→DATETIME、SERIAL→INTEGER AUTOINCREMENT、halfvec 向量列删除等。46 张 = 53 张减去 7 张不适用于 Lite 模式的表：
  `embeddings`（依赖 pgvector halfvec）、`organization_members`、`task_pending_ops`、`task_dead_letters`、`system_settings`、`knowledge_processing_spans`、`knowledge_tag_relations`。
- **MySQL 版 = 遗留精简脚本**。只有 10 张最核心的表（tenants、models、knowledge_bases、knowledges、sessions、messages、message_suggestion_sets、message_suggestion_events、chunks、chunk_revisions），是早期版本留下的引导脚本，**没有跟上后续 60+ 个迁移**。代码层面主数据库驱动只接受 `postgres` / `sqlite`（`internal/container/container.go` 中 `DB_DRIVER` 的 switch 分支），MySQL 驱动仅注册给 **Doris 分析库**使用，因此 MySQL 脚本对当前版本**没有实际作用**。

**结论：对你当前的 ParadeDB 部署，本文档的 53 张表就是完整准确的表结构；MySQL/SQLite 的内容可以完全忽略。**

## 一、租户 / 用户 / 认证 / 权限

### tenants

**用途**：系统多租户核心。存储配额、全局 Agent/检索/存储配置；api_key 字段已在 000065 迁移中迁入 tenant_api_keys 表后删除。

**来源**：创建于 `000000_init.up.sql`；后续修改：`000001_agent.up.sql`, `000013_engine_configs.up.sql`, `000018_extend_tenant_api_key.up.sql`, `000020_add_message_knowledge_id.up.sql`, `000035_add_credentials.up.sql`, `000064_principal_model.up.sql`, `000065_tenant_api_keys.up.sql`, `000068_storage_backends.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PRIMARY KEY | 租户自增主键 |
| `name` | VARCHAR(255) | NOT NULL | 租户名称 |
| `description` | TEXT | - | 租户描述 |
| `retriever_engines` | JSONB | NOT NULL DEFAULT '[]' | 检索引擎配置列表 (JSONB) |
| `status` | VARCHAR(50) | DEFAULT 'active' | 状态：active/inactive 等 |
| `business` | VARCHAR(255) | NOT NULL | 业务标识 |
| `storage_quota` | BIGINT | NOT NULL DEFAULT 10737418240 | 存储配额（字节），默认 10GB |
| `storage_used` | BIGINT | NOT NULL DEFAULT 0 | 已使用存储（字节） |
| `agent_config` | JSONB | DEFAULT NULL | 租户级 Agent 配置（JSONB） *Tenant-level agent configuration in JSON format* |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `context_config` | JSONB | - | 全局 Context 配置（会话默认模板） *Global Context configuration for this tenant (default for all sessions)* |
| `conversation_config` | JSONB | - | 全局会话配置（普通模式会话默认值） *Global Conversation configuration for this tenant (default for normal mode sessions)* |
| `web_search_config` | JSONB | DEFAULT NULL | Web 搜索配置 *Web search configuration for the tenant* |
| `parser_engine_config` | JSONB | DEFAULT NULL | 解析引擎覆盖配置（mineru_endpoint 等） *Parser engine overrides (mineru_endpoint, mineru_api_key, etc.); takes precedence over env when parsing* |
| `storage_engine_config` | JSONB | DEFAULT NULL | 存储引擎参数（Local/MinIO/COS） *Storage engine parameters for Local, MinIO, COS; used for document/file storage and docreader* |
| `chat_history_config` | JSONB | - | 聊天历史配置 |
| `retrieval_config` | JSONB | - | 检索配置 |
| `credentials` | JSONB | DEFAULT NULL | 租户级凭据存储（JSONB） *Third-party provider credentials (e.g. WeKnoraCloud AppID/AppSecret); encrypted at application level* |
| `api_principal_config` | JSONB | - | API 主体验证配置（MCP OAuth / API Key） |
| `default_storage_backend_id` | VARCHAR(36) | - | 默认存储后端 ID（关联 storage_backends.id） |

**主键**：`id`

**索引（2）**：`idx_tenants_api_key(api_key)`、`idx_tenants_status(status)`

### users

**用途**：用户账户，可跨租户（can_access_all_tenants），is_system_admin 为平台级管理员。

**来源**：创建于 `000001_agent.up.sql`；后续修改：`000001_agent.up.sql`, `000049_user_preferences.up.sql`, `000053_system_admin_and_settings.up.sql`

> 数据库注释：*User accounts in the system*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 用户 ID（UUID） *Unique identifier of the user* |
| `username` | VARCHAR(100) | NOT NULL | 用户名（唯一） *Username of the user* |
| `email` | VARCHAR(255) | NOT NULL | 邮箱（唯一） *Email address of the user* |
| `password_hash` | VARCHAR(255) | NOT NULL | 密码哈希 *Hashed password of the user* |
| `avatar` | VARCHAR(500) | - | 头像 URL *Avatar URL of the user* |
| `tenant_id` | INTEGER | - | 主租户 ID（可空，跨租户用户） *Tenant ID that the user belongs to* |
| `is_active` | BOOLEAN | NOT NULL DEFAULT true | 是否激活 *Whether the user is active* |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `can_access_all_tenants` | BOOLEAN | NOT NULL DEFAULT FALSE | 是否可访问所有租户 |
| `preferences` | JSONB | NOT NULL DEFAULT '{}'::jsonb | 用户偏好（JSONB） *Per-user JSON preferences (memory toggle, future UI knobs)* |
| `is_system_admin` | BOOLEAN | NOT NULL DEFAULT FALSE | 是否为系统管理员 *Whether the user is a system administrator (independent of tenant roles)* |

**主键**：`id`

**索引（5）**：`idx_users_username(username)`、`idx_users_email(email)`、`idx_users_tenant_id(tenant_id)`、`idx_users_deleted_at(deleted_at)`、`idx_users_is_system_admin(is_system_admin)`

### auth_tokens

**用途**：登录令牌（access/refresh），支持撤销。

**来源**：创建于 `000001_agent.up.sql`；后续修改：`000001_agent.up.sql`

> 数据库注释：*Authentication tokens for users*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 令牌 ID（UUID） *Unique identifier of the token* |
| `user_id` | VARCHAR(36) | NOT NULL | 所属用户 ID *User ID that owns this token* |
| `token` | TEXT | NOT NULL | 令牌值（JWT 等） *Token value (JWT or other format)* |
| `token_type` | VARCHAR(50) | NOT NULL | 类型：access_token / refresh_token *Token type (access_token, refresh_token)* |
| `expires_at` | TIMESTAMP WITH TIME ZONE | NOT NULL | 过期时间 *Token expiration time* |
| `is_revoked` | BOOLEAN | NOT NULL DEFAULT false | 是否已撤销 *Whether the token is revoked* |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**主键**：`id`

**索引（4）**：`idx_auth_tokens_user_id(user_id)`、`idx_auth_tokens_token(token)`、`idx_auth_tokens_token_type(token_type)`、`idx_auth_tokens_expires_at(expires_at)`

### tenant_members

**用途**：租户内成员与角色（owner/admin/contributor/viewer），RBAC 模型。

**来源**：创建于 `000043_tenant_rbac.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PRIMARY KEY | 成员关系 ID |
| `user_id` | VARCHAR(36) | NOT NULL | 用户 ID |
| `tenant_id` | INTEGER | NOT NULL | 租户 ID |
| `role` | VARCHAR(20) | NOT NULL DEFAULT 'contributor' | 角色：owner / admin / contributor / viewer |
| `status` | VARCHAR(20) | NOT NULL DEFAULT 'active' | 状态：active / invited 等 |
| `invited_by` | VARCHAR(36) | - | 邀请者 |
| `joined_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 加入时间 |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |

**主键**：`id`

**索引（3）**：`idx_tenant_members_user_tenant_unique(user_id, tenant_id)`、`idx_tenant_members_tenant_role(tenant_id, role)`、`idx_tenant_members_user(user_id)`

### tenant_invitations

**用途**：租户邀请（定向邀请 + 分享链接两种模式）。

**来源**：创建于 `000048_tenant_invitations.up.sql`；后续修改：`000054_invitation_tokens.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PRIMARY KEY | 邀请 ID |
| `tenant_id` | INTEGER | NOT NULL | 租户 ID |
| `invitee_user_id` | VARCHAR(36) | NOT NULL | 被邀请用户 ID（分享链接行可为空串） |
| `invited_by` | VARCHAR(36) | - | 邀请者 |
| `role` | VARCHAR(20) | NOT NULL | 授予角色 |
| `status` | VARCHAR(20) | NOT NULL DEFAULT 'pending' | 状态：pending / accepted / rejected / revoked |
| `message` | VARCHAR(500) | - | 留言 |
| `expires_at` | TIMESTAMP WITH TIME ZONE | NOT NULL | 过期时间 |
| `responded_at` | TIMESTAMP WITH TIME ZONE | - | 响应时间 |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `token` | VARCHAR(64) | NOT NULL DEFAULT '' | 分享链接注册令牌（明文，短 TTL） |
| `accepted_count` | INTEGER | NOT NULL DEFAULT 0 | 通过该邀请完成注册的人数（分享链接累积） |

**主键**：`id`

**索引（4）**：`idx_tenant_invitations_unique_pending(tenant_id, invitee_user_id)`、`idx_tenant_invitations_tenant(tenant_id)`、`idx_tenant_invitations_invitee(invitee_user_id)`、`idx_tenant_invitations_token(token)`

### tenant_api_keys

**用途**：租户/平台级 API Key 管理（哈希 + 白名单 + 能力授权）。

**来源**：创建于 `000065_tenant_api_keys.up.sql`；后续修改：`000071_platform_api_keys.up.sql`, `000072_auth_timestamp_tz.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PRIMARY KEY | API Key 记录 ID |
| `tenant_id` | INTEGER | NOT NULL REFERENCES tenants(id) ON DELETE CASCADE | 租户 ID（scope_type=platform 时为 NULL） |
| `name` | VARCHAR(128) | NOT NULL | Key 名称 |
| `key_hash` | VARCHAR(64) | NOT NULL UNIQUE | Key 哈希（唯一） |
| `api_key` | TEXT | NOT NULL DEFAULT '' | 原始 Key（加密存储） |
| `full_access` | BOOLEAN | NOT NULL DEFAULT FALSE | 是否全量权限（platform 级别必须为 FALSE） |
| `knowledge_base_ids` | JSONB | NOT NULL DEFAULT '[]'::jsonb | 允许访问的知识库 ID 白名单（JSONB） |
| `capabilities` | JSONB | NOT NULL DEFAULT '[]'::jsonb | 能力清单（JSONB，非全量 Key 的受限授权） |
| `last_used_at` | TIMESTAMP | - | 最后使用时间 |
| `expires_at` | TIMESTAMP | - | 过期时间 |
| `revoked_at` | TIMESTAMP | - | 撤销时间 |
| `created_at` | TIMESTAMP | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | NOT NULL DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `scope_type` | VARCHAR(16) | NOT NULL DEFAULT 'tenant' | 作用域：tenant / platform |

**主键**：`id`

**索引（3）**：`idx_tenant_api_keys_tenant(tenant_id)`、`idx_tenant_api_keys_revoked_at(revoked_at)`、`idx_tenant_api_keys_scope_type(scope_type)`

### system_settings

**用途**：平台级设置（键值 JSONB），仅系统管理员可改。

**来源**：创建于 `000053_system_admin_and_settings.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PRIMARY KEY | 设置 ID |
| `key` | VARCHAR(128) | NOT NULL UNIQUE | 设置键（唯一） |
| `value` | JSONB | NOT NULL | 值（JSONB） |
| `value_type` | VARCHAR(16) | NOT NULL | 值类型：int / string / bool / array / object |
| `category` | VARCHAR(32) | NOT NULL | 分类 |
| `description` | TEXT | NOT NULL DEFAULT '' | 描述 |
| `is_secret` | BOOLEAN | NOT NULL DEFAULT false | 是否机密 |
| `requires_restart` | BOOLEAN | NOT NULL DEFAULT false | 是否需要重启生效 |
| `last_modified_by` | VARCHAR(36) | NOT NULL DEFAULT '' | 最后修改人 |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**主键**：`id`

**索引（1）**：`idx_system_settings_category(category)`

### audit_logs

**用途**：操作审计（谁在何时做了什么，含请求路径）。

**来源**：创建于 `000044_audit_log.up.sql`；后续修改：`000073_kb_activity_scope.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PRIMARY KEY | 审计日志 ID |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `actor_user_id` | VARCHAR(36) | NOT NULL DEFAULT '' | 操作者用户 ID |
| `actor_role` | VARCHAR(32) | NOT NULL DEFAULT '' | 操作者角色 |
| `action` | VARCHAR(64) | NOT NULL | 操作名 |
| `target_type` | VARCHAR(32) | NOT NULL DEFAULT '' | 目标类型 |
| `target_id` | VARCHAR(64) | NOT NULL DEFAULT '' | 目标 ID |
| `target_user_id` | VARCHAR(36) | NOT NULL DEFAULT '' | 目标用户 ID |
| `request_path` | VARCHAR(512) | NOT NULL DEFAULT '' | 请求路径 |
| `request_method` | VARCHAR(16) | NOT NULL DEFAULT '' | HTTP 方法 |
| `outcome` | VARCHAR(16) | NOT NULL DEFAULT 'success' | 结果：success / failure |
| `details` | JSONB | NOT NULL DEFAULT '{}'::JSONB | 详情（JSONB） |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `scope_type` | VARCHAR(32) | NOT NULL DEFAULT '' | 作用域类型 |
| `scope_id` | VARCHAR(64) | NOT NULL DEFAULT '' | 作用域 ID |

**主键**：`id`

**索引（5）**：`idx_audit_logs_tenant_id_desc(tenant_id, id DESC)`、`idx_audit_logs_actor(actor_user_id)`、`idx_audit_logs_tenant_action(tenant_id, action)`、`idx_audit_logs_created_at(created_at)`、`idx_audit_logs_tenant_scope_desc(tenant_id, scope_type, scope_id, id DESC)`


---

## 二、模型配置

### models

**用途**：模型注册中心。type 决定用途（KnowledgeQA/Embedding/Rerank），tenant_id=0 表示系统内置模型。

**来源**：创建于 `000000_init.up.sql`；后续修改：`000001_agent.up.sql`, `000052_models_managed_by.up.sql`, `000057_models_display_name.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(64) | PRIMARY KEY DEFAULT uuid_generate_v4() | 模型 ID（UUID） |
| `tenant_id` | INTEGER | NOT NULL | 所属租户 ID |
| `name` | VARCHAR(255) | NOT NULL | 模型名称（标识符） |
| `display_name` | VARCHAR(255) | NOT NULL DEFAULT '' | 展示名称 |
| `type` | VARCHAR(50) | NOT NULL | 模型类型：KnowledgeQA / Embedding / Rerank / ASR / VLM 等 |
| `source` | VARCHAR(50) | NOT NULL | 模型来源：OpenAI / Ollama / 自定义 等 |
| `description` | TEXT | - | 模型描述 |
| `parameters` | JSONB | NOT NULL | 模型参数（JSONB，如 base_url、api_key 等） |
| `is_default` | BOOLEAN | NOT NULL DEFAULT false | 是否为默认模型 |
| `status` | VARCHAR(50) | NOT NULL DEFAULT 'active' | 状态：active/inactive |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `is_builtin` | BOOLEAN | NOT NULL DEFAULT false | 是否为内置模型 |
| `managed_by` | VARCHAR(32) | NOT NULL DEFAULT '' | 托管方标识 |

**主键**：`id`

**索引（4）**：`idx_models_type(type)`、`idx_models_source(source)`、`idx_models_is_builtin(is_builtin)`、`idx_models_managed_by_yaml(managed_by)`


---

## 三、知识库 / 文档 / 切块 / 向量

### knowledge_bases

**用途**：知识库容器。继承租户级模型/存储配置，可覆盖；type 区分 document/faq。

**来源**：创建于 `000000_init.up.sql`；后续修改：`000001_agent.up.sql`, `000004_drop_vlm_model_id.up.sql`, `000014_storage_provider_config.up.sql`, `000016_add_kb_pinned.up.sql`, `000031_add_asr_config.up.sql`, `000036_kb_vector_store_id.up.sql`, `000037_wiki_and_indexing.up.sql`, `000043_tenant_rbac.up.sql`, `000068_storage_backends.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 知识库 ID（UUID） |
| `name` | VARCHAR(255) | NOT NULL | 知识库名称 |
| `description` | TEXT | - | 知识库描述 |
| `tenant_id` | INTEGER | NOT NULL | 所属租户 ID |
| `embedding_model_id` | VARCHAR(64) | NOT NULL | Embedding 模型 ID |
| `summary_model_id` | VARCHAR(64) | NOT NULL | Summary 模型 ID |
| `cos_config` | JSONB | NOT NULL DEFAULT '{}' | COS 对象存储配置（历史字段） |
| `vlm_config` | JSONB | NOT NULL DEFAULT '{}' | VLM（视觉大模型）配置（model_id 等） |
| `extract_config` | JSONB | NULL DEFAULT NULL | 知识抽取配置 |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `is_temporary` | BOOLEAN | NOT NULL DEFAULT false | 是否临时知识库（UI 隐藏） *Whether this knowledge base is temporary (ephemeral) and should be hidden from UI* |
| `type` | VARCHAR(32) | NOT NULL DEFAULT 'document' | 知识库类型：document / faq / hybrid 等 |
| `faq_config` | JSONB | - | FAQ 类型配置 |
| `question_generation_config` | JSONB | NULL | 问题生成配置 |
| `storage_provider_config` | JSONB | DEFAULT NULL | 存储提供方配置（provider 名，凭据来自租户级配置） *Storage provider config for this KB. Only stores provider name; credentials come from tenant StorageEngineConfig.* |
| `is_pinned` | BOOLEAN | NOT NULL DEFAULT false | 是否被平台置顶 |
| `pinned_at` | TIMESTAMP WITH TIME ZONE | NULL | 置顶时间 |
| `asr_config` | JSONB | - | ASR 语音识别配置 *ASR (Automatic Speech Recognition) configuration: {"enabled": bool, "model_id": string, "language": string}* |
| `vector_store_id` | VARCHAR(36) | - | 关联的向量库 ID（vector_stores.id） *References vector_stores.id. NULL means tenant default (env store derived from RETRIEVE_DRIVER). * |
| `wiki_config` | JSONB | - | Wiki 配置 *Wiki configuration: {"auto_ingest": bool, "synthesis_model_id": string, "wiki_language": string, "max_pages_per_ingest": int}* |
| `indexing_strategy` | JSONB | - | 索引策略（vector_enabled/keyword_enabled/wiki_enabled/graph_enabled 等） *Indexing pipelines strategy: {"vector_enabled": bool, "keyword_enabled": bool, "wiki_enabled": bool, "graph_enabled": bool}* |
| `creator_id` | VARCHAR(36) | - | 创建者用户 ID |
| `storage_backend_id` | VARCHAR(36) | - | 存储后端 ID（storage_backends.id） |

**主键**：`id`

**索引（4）**：`idx_knowledge_bases_tenant_id(tenant_id)`、`idx_knowledge_bases_tenant_vector_store(tenant_id, vector_store_id)`、`idx_knowledge_bases_tenant_creator(tenant_id, creator_id)`、`idx_knowledge_bases_storage_backend(tenant_id, storage_backend_id)`

### knowledges

**用途**：知识库内的文档/FAQ 条目。parse_status 生命周期：unprocessed→processing→finalizing→completed。

**来源**：创建于 `000000_init.up.sql`；后续修改：`000001_agent.up.sql`, `000009_add_last_faq_import_result.up.sql`, `000025_message_channel.up.sql`, `000056_knowledge_pending_subtasks.up.sql`, `000058_expand_knowledge_source.up.sql`, `000063_knowledge_multi_tags.up.sql`, `000078_chunk_editing_and_custom_metadata.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 知识条目 ID（UUID） |
| `tenant_id` | INTEGER | NOT NULL | 所属租户 ID |
| `knowledge_base_id` | VARCHAR(36) | NOT NULL | 所属知识库 ID |
| `type` | VARCHAR(50) | NOT NULL | 类型：document / faq / chat_history 等 |
| `title` | VARCHAR(255) | NOT NULL | 标题 |
| `description` | TEXT | - | 描述 |
| `source` | VARCHAR(2048) | NOT NULL | 来源（URL/路径/内容） |
| `parse_status` | VARCHAR(50) | NOT NULL DEFAULT 'unprocessed' | 解析状态：unprocessed/processing/finalizing/completed/failed |
| `enable_status` | VARCHAR(50) | NOT NULL DEFAULT 'enabled' | 启用状态：enabled/disabled |
| `embedding_model_id` | VARCHAR(64) | - | 使用的 Embedding 模型（可覆盖知识库级配置） |
| `file_name` | VARCHAR(255) | - | 文件名 |
| `file_type` | VARCHAR(50) | - | 文件类型/扩展名 |
| `file_size` | BIGINT | - | 文件大小（字节） |
| `file_path` | TEXT | - | 文件存储路径 |
| `file_hash` | VARCHAR(64) | - | 文件内容哈希 |
| `storage_size` | BIGINT | NOT NULL DEFAULT 0 | 存储大小（字节） |
| `metadata` | JSONB | - | 元数据（JSONB） |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `processed_at` | TIMESTAMP WITH TIME ZONE | - | 处理完成时间 |
| `error_message` | TEXT | - | 错误信息 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `summary_status` | VARCHAR(32) | DEFAULT 'none' | 摘要生成状态：none/summarizing/completed/failed |
| `last_faq_import_result` | JSON | DEFAULT NULL | 最近一次 FAQ 导入结果（JSON） |
| `channel` | VARCHAR(50) | NOT NULL DEFAULT 'web' | 来源渠道：web / im / api 等 *Source channel of the knowledge: web, api, browser_extension, wechat, etc.* |
| `pending_subtasks_count` | INT | NOT NULL DEFAULT 0 | 未完成的富化子任务数（parse_status=finalizing 时 >0） |
| `custom_metadata` | JSONB | NOT NULL DEFAULT '{}'::JSONB | 自定义元数据（JSONB） |

**主键**：`id`

**索引（7）**：`idx_knowledges_tenant_id(tenant_id)`、`idx_knowledges_base_id(knowledge_base_id)`、`idx_knowledges_parse_status(parse_status)`、`idx_knowledges_enable_status(enable_status)`、`idx_knowledges_tag(tag_id)`、`idx_knowledges_summary_status(summary_status)`、`idx_knowledges_kb_metadata_external_id(knowledge_base_id, (metadata->>'external_id')`

### chunks

**用途**：知识切块（文本/表格/图像），支持父子层级与前后链，seq_id 供外部 API 使用。

**来源**：创建于 `000000_init.up.sql`；后续修改：`000001_agent.up.sql`, `000003_chunk_flags.up.sql`, `000010_add_seq_id.up.sql`, `000033_add_video_info_to_chunks.up.sql`, `000078_chunk_editing_and_custom_metadata.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 块 ID（UUID） |
| `tenant_id` | INTEGER | NOT NULL | 所属租户 ID |
| `knowledge_base_id` | VARCHAR(36) | NOT NULL | 所属知识库 ID |
| `knowledge_id` | VARCHAR(36) | NOT NULL | 所属知识条目 ID |
| `content` | TEXT | NOT NULL | 块内容 |
| `chunk_index` | INTEGER | NOT NULL | 块在文档中的序号 |
| `is_enabled` | BOOLEAN | NOT NULL DEFAULT true | 是否启用 |
| `start_at` | INTEGER | NOT NULL | 起始位置（字符偏移） |
| `end_at` | INTEGER | NOT NULL | 结束位置 |
| `pre_chunk_id` | VARCHAR(36) | - | 前一块 ID |
| `next_chunk_id` | VARCHAR(36) | - | 后一块 ID |
| `chunk_type` | VARCHAR(20) | NOT NULL DEFAULT 'text' | 块类型：text/table/image/faq 等 |
| `parent_chunk_id` | VARCHAR(36) | - | 父块 ID（支持层级） |
| `image_info` | TEXT | - | 图像信息（多模态） |
| `relation_chunks` | JSONB | - | 关联块（JSONB） |
| `indirect_relation_chunks` | JSONB | - | 间接关联块（JSONB） |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `metadata` | JSONB | - | 元数据（JSONB） |
| `tag_id` | VARCHAR(36) | - | 标签 ID（knowledge_tags.id，弃用中） |
| `status` | INT | NOT NULL DEFAULT 0 | 块处理状态（INT，0 正常） |
| `content_hash` | VARCHAR(64) | - | 内容哈希 |
| `flags` | INTEGER | NOT NULL DEFAULT 1 | 位标志（bit 1=推荐等，默认 1） |
| `seq_id` | BIGINT | - | 对外 API 使用的自增 ID（bigint） |
| `video_info` | TEXT | - | 视频信息 *Video information in JSON format: {"url": string, "frame_count": int, "has_vlm_analysis": bool, "has_asr": bool, "video_summary": string, "asr_text": string, "frame_descriptions": string[]}* |
| `source_content` | TEXT | NOT NULL DEFAULT '' | 原始内容（未编辑的源文本） |
| `content_revision` | INT | NOT NULL DEFAULT 0 | 内容修订号（编辑历史） |
| `index_status` | VARCHAR(16) | NOT NULL DEFAULT 'ready' | 索引状态：ready/pending/failed 等 |
| `last_editor_id` | VARCHAR(64) | NOT NULL DEFAULT '' | 最近编辑者 ID |
| `context_header` | TEXT | NOT NULL DEFAULT '' | 上下文标题（编辑时保留的标题） |

**主键**：`id`

**索引（8）**：`idx_chunks_tenant_kg(tenant_id, knowledge_id)`、`idx_chunks_parent_id(parent_chunk_id)`、`idx_chunks_chunk_type(chunk_type)`、`idx_chunks_tag(tag_id)`、`idx_chunks_content_hash(content_hash)`、`idx_chunks_seq_id(seq_id)`、`idx_chunks_kb_tenant(knowledge_base_id, tenant_id)`、`idx_chunks_knowledge_enabled(knowledge_id, is_enabled, deleted_at)`

### chunk_revisions

**用途**：块编辑修订历史（chunk 手动编辑后回溯）。

**来源**：创建于 `000078_chunk_editing_and_custom_metadata.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY | 修订 ID |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `knowledge_base_id` | VARCHAR(36) | NOT NULL | 知识库 ID |
| `knowledge_id` | VARCHAR(36) | NOT NULL | 知识条目 ID |
| `chunk_id` | VARCHAR(36) | NOT NULL | 块 ID |
| `revision` | INT | NOT NULL | 修订号 |
| `content` | TEXT | NOT NULL DEFAULT '' | 内容 |
| `is_enabled` | BOOLEAN | NOT NULL DEFAULT TRUE | 是否启用 |
| `editor_id` | VARCHAR(64) | NOT NULL DEFAULT '' | 编辑者 ID |
| `edit_source` | VARCHAR(16) | NOT NULL DEFAULT 'user' | 编辑来源：user 等 |
| `edited_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT NOW() | 编辑时间 |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT NOW() | 创建时间 |

**主键**：`id`

**索引（2）**：`idx_chunk_revisions_chunk_revision(chunk_id, revision)`、`idx_chunk_revisions_tenant_chunk(tenant_id, chunk_id)`

### embeddings

**用途**：向量索引核心表（PostgreSQL pgvector）。维度分区 HNSW 索引 + BM25 全文检索（pg_search）。

**来源**：创建于 `000002_embeddings.up.sql`；后续修改：`000002_embeddings.up.sql`, `000007_embeddings_tag_id.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | SERIAL | PRIMARY KEY | 自增主键 |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `source_id` | VARCHAR(64) | NOT NULL | 来源 ID（chunk/knowledge id） |
| `source_type` | INTEGER | NOT NULL | 来源类型（枚举：chunk 等） |
| `chunk_id` | VARCHAR(64) | - | 块 ID |
| `knowledge_id` | VARCHAR(64) | - | 知识条目 ID |
| `knowledge_base_id` | VARCHAR(64) | - | 知识库 ID |
| `content` | TEXT | - | 文本内容（BM25 检索用） |
| `dimension` | INTEGER | NOT NULL | 向量维度 |
| `embedding` | halfvec | - | 向量（halfvec 半精度浮点） |
| `is_enabled` | BOOLEAN | DEFAULT TRUE | 是否启用 |
| `tag_id` | VARCHAR(36) | - | 标签 ID（FAQ 优先级过滤） |

**主键**：`id`

**索引（4）**：`embeddings_unique_source(source_id, source_type)`、`idx_embeddings_is_enabled(is_enabled)`、`idx_embeddings_knowledge_base_id(knowledge_base_id)`、`idx_embeddings_tag_id(tag_id)`

### knowledge_tags

**用途**：知识库内标签，用于 FAQ 分类与过滤。

**来源**：创建于 `000001_agent.up.sql`；后续修改：`000010_add_seq_id.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY | 标签 ID（UUID PK，无默认值） |
| `tenant_id` | INTEGER | NOT NULL | 租户 ID |
| `knowledge_base_id` | VARCHAR(36) | NOT NULL | 知识库 ID |
| `name` | VARCHAR(128) | NOT NULL | 标签名（库内唯一） |
| `color` | VARCHAR(32) | - | 标签颜色 |
| `sort_order` | INTEGER | NOT NULL DEFAULT 0 | 排序 |
| `created_at` | TIMESTAMPTZ | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMPTZ | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMPTZ | - | 软删除时间 |
| `seq_id` | BIGINT | - | 对外 API 自增 ID |

**主键**：`id`

**索引（3）**：`idx_knowledge_tags_kb_name(tenant_id, knowledge_base_id, name)`、`idx_knowledge_tags_kb(tenant_id, knowledge_base_id)`、`idx_knowledge_tags_seq_id(seq_id)`

### knowledge_tag_relations

**用途**：知识条目-标签多对多关系表（替代 knowledges.tag_id 单值字段）。

**来源**：创建于 `000063_knowledge_multi_tags.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `knowledge_id` | VARCHAR(36) | NOT NULL | 知识条目 ID |
| `tag_id` | VARCHAR(36) | NOT NULL | 标签 ID |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT NOW() | 创建时间 |


**表级约束**：`PRIMARY KEY (knowledge_id, tag_id)`

**索引（2）**：`idx_ktr_knowledge(knowledge_id)`、`idx_ktr_tag(tag_id)`

### temporary_documents

**用途**：会话中暂存的上传文档（处理后过期清理）。

**来源**：创建于 `000070_temporary_documents.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | NOT NULL PRIMARY KEY | 临时文档 ID |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `session_id` | VARCHAR(36) | NOT NULL | 会话 ID |
| `resource_ref` | TEXT | NOT NULL | 资源引用 |
| `file_name` | VARCHAR(1024) | NOT NULL | 文件名 |
| `file_type` | VARCHAR(32) | NOT NULL | 文件类型 |
| `mime_type` | VARCHAR(255) | NOT NULL DEFAULT '' | MIME 类型 |
| `file_size` | BIGINT | NOT NULL | 大小（字节） |
| `status` | VARCHAR(16) | NOT NULL DEFAULT 'uploaded' | 状态：uploaded / processing / ready / failed / expired |
| `content` | TEXT | NOT NULL DEFAULT '' | 抽取内容 |
| `chunks` | JSONB | NOT NULL DEFAULT '[]'::jsonb | 切块结果（JSONB） |
| `image_refs` | JSONB | NOT NULL DEFAULT '[]'::jsonb | 图片引用（JSONB） |
| `metadata` | JSONB | NOT NULL DEFAULT '{}'::jsonb | 元数据（JSONB） |
| `processing_options` | JSONB | NOT NULL DEFAULT '{}'::jsonb | 处理选项（JSONB） |
| `token_count` | INTEGER | NOT NULL DEFAULT 0 | Token 数 |
| `chunk_count` | INTEGER | NOT NULL DEFAULT 0 | 块数 |
| `error_message` | TEXT | NOT NULL DEFAULT '' | 错误信息 |
| `expires_at` | TIMESTAMP | NOT NULL | 过期时间 |
| `started_at` | TIMESTAMP | NULL | 开始处理时间 |
| `ready_at` | TIMESTAMP | NULL | 就绪时间 |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP | NULL | 软删除时间 |

**主键**：`id`

**索引（3）**：`idx_temporary_documents_scope(tenant_id, session_id)`、`idx_temporary_documents_status(status)`、`idx_temporary_documents_expires(expires_at)`

### vector_stores

**用途**：外部向量库注册（pgvector/ES/Milvus 等），知识库可选绑定。

**来源**：创建于 `000032_vector_stores.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | NOT NULL PRIMARY KEY | 向量库 ID |
| `name` | VARCHAR(255) | NOT NULL | 向量库名 |
| `engine_type` | VARCHAR(50) | NOT NULL | 引擎类型：pgvector / elasticsearch / milvus 等 |
| `connection_config` | JSONB | NOT NULL DEFAULT '{}' | 连接配置（JSONB） |
| `index_config` | JSONB | NOT NULL DEFAULT '{}' | 索引配置（JSONB） |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID（0=系统级） |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP | NULL | 软删除时间 |

**主键**：`id`

**索引（4）**：`idx_vector_stores_name_tenant(name, tenant_id)`、`idx_vector_stores_tenant_id(tenant_id)`、`idx_vector_stores_engine_type(engine_type)`、`idx_vector_stores_deleted_at(deleted_at)`


---

## 四、会话 / 消息 / 问答

### sessions

**用途**：问答会话，绑定知识库与 Agent，携带检索参数（阈值、top_k）与兜底策略。

**来源**：创建于 `000000_init.up.sql`；后续修改：`000001_agent.up.sql`, `000006_custom_agents.up.sql`, `000039_session_user_id_and_pin.up.sql`, `000064_principal_model.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 会话 ID（UUID） |
| `tenant_id` | INTEGER | NOT NULL | 所属租户 ID |
| `title` | VARCHAR(255) | - | 会话标题 |
| `description` | TEXT | - | 会话描述 |
| `knowledge_base_id` | VARCHAR(36) | - | 绑定的知识库 ID |
| `max_rounds` | INTEGER | NOT NULL DEFAULT 5 | 最大历史轮数（默认 5） |
| `enable_rewrite` | BOOLEAN | NOT NULL DEFAULT true | 是否启用问题改写（默认 true） |
| `fallback_strategy` | VARCHAR(255) | NOT NULL DEFAULT 'fixed' | 兜底策略：fixed / model 等 |
| `fallback_response` | TEXT | NOT NULL DEFAULT '很抱歉，我暂时无法回答这个问题。' | 兜底回复文本（默认中文提示） |
| `keyword_threshold` | FLOAT | NOT NULL DEFAULT 0.5 | 关键词检索阈值（默认 0.5） |
| `vector_threshold` | FLOAT | NOT NULL DEFAULT 0.5 | 向量检索阈值（默认 0.5） |
| `rerank_model_id` | VARCHAR(64) | - | Rerank 模型 ID |
| `embedding_top_k` | INTEGER | NOT NULL DEFAULT 10 | Embedding 召回数量（默认 10） |
| `rerank_top_k` | INTEGER | NOT NULL DEFAULT 10 | Rerank 保留数量（默认 10） |
| `rerank_threshold` | FLOAT | NOT NULL DEFAULT 0.65 | Rerank 阈值（默认 0.65） |
| `summary_model_id` | VARCHAR(64) | - | 摘要模型 ID |
| `summary_parameters` | JSONB | NOT NULL DEFAULT '{}' | 摘要参数（JSONB） |
| `agent_config` | JSONB | DEFAULT NULL | 会话级 Agent 配置（JSONB） *Session-level agent configuration in JSON format* |
| `context_config` | JSONB | DEFAULT NULL | 上下文管理配置（JSONB） *LLM context management configuration (separate from message storage)* |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `agent_id` | VARCHAR(36) | - | 使用的 Agent ID（custom_agents.id） |
| `user_id` | VARCHAR(512) | - | 所属用户 ID（可为空） |
| `is_pinned` | BOOLEAN | NOT NULL DEFAULT FALSE | 用户是否置顶该会话 |
| `pinned_at` | TIMESTAMP WITH TIME ZONE | - | 置顶时间 |

**主键**：`id`

**索引（3）**：`idx_sessions_tenant_id(tenant_id)`、`idx_sessions_agent_id(agent_id)`、`idx_sessions_tenant_user_pin(tenant_id, user_id, is_pinned DESC, pinned_at DESC, updated_at DESC)`

### messages

**用途**：会话消息，含知识引用、Agent 步骤、渲染内容、附件等。

**来源**：创建于 `000000_init.up.sql`；后续修改：`000001_agent.up.sql`, `000005_mentioned_items.up.sql`, `000015_add_is_fallback.up.sql`, `000019_add_agent_duration_ms.up.sql`, `000020_add_message_knowledge_id.up.sql`, `000022_message_images.up.sql`, `000025_message_channel.up.sql`, `000027_message_rendered_content.up.sql`, `000034_add_attachments.up.sql`, `000067_question_suggestions.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 消息 ID（UUID） |
| `request_id` | VARCHAR(36) | NOT NULL | 请求 ID |
| `session_id` | VARCHAR(36) | NOT NULL | 所属会话 ID |
| `role` | VARCHAR(50) | NOT NULL | 角色：user / assistant / system |
| `content` | TEXT | NOT NULL | 消息内容 |
| `knowledge_references` | JSONB | NOT NULL DEFAULT '[]' | 引用的知识块引用（JSONB 数组） |
| `agent_steps` | JSONB | DEFAULT NULL | Agent 执行步骤（推理过程与工具调用，JSONB） *Agent execution steps (reasoning process and tool calls)* |
| `is_completed` | BOOLEAN | NOT NULL DEFAULT false | 是否已完成 |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `mentioned_items` | JSONB | DEFAULT '[]' | @提及的知识库与文件（JSONB） *Stores @mentioned knowledge bases and files (id, name, type) when user sends a message* |
| `is_fallback` | BOOLEAN | DEFAULT FALSE | 是否走兜底回复 |
| `agent_duration_ms` | BIGINT | DEFAULT 0 | Agent 执行耗时（毫秒） |
| `knowledge_id` | VARCHAR(36) | - | 关联的知识条目 ID（聊天历史入库） |
| `images` | JSONB | DEFAULT '[]' | 消息中的图片（JSONB） |
| `channel` | VARCHAR(50) | NOT NULL DEFAULT '' | 消息渠道：web / im 等 *Source channel of the message: web, api, im, etc.* |
| `rendered_content` | TEXT | NOT NULL DEFAULT '' | 渲染后的内容（富文本/HTML） *Full RAG-augmented user message sent to LLM, preserving retrieval context across turns* |
| `attachments` | JSONB | DEFAULT '[]'::jsonb | 附件（JSONB 数组） |
| `agent_id` | VARCHAR(36) | NOT NULL DEFAULT '' | 生成该消息的 Agent ID |
| `agent_tenant_id` | INTEGER | NOT NULL DEFAULT 0 | Agent 所属租户 ID |
| `model_id` | VARCHAR(64) | NOT NULL DEFAULT '' | 生成该消息的模型 ID |
| `execution_context` | JSONB | NOT NULL DEFAULT '{}'::jsonb | 执行上下文（JSONB） |

**主键**：`id`

**索引（3）**：`idx_messages_session_id(session_id)`、`idx_messages_knowledge_id(knowledge_id)`、`idx_messages_agent_id(agent_id)`

### message_suggestion_sets

**用途**：助手消息的推荐问题缓存（去重键 config_hash+placement+locale）。

**来源**：创建于 `000067_question_suggestions.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 推荐问题集 ID |
| `tenant_id` | INTEGER | NOT NULL REFERENCES tenants(id) ON DELETE CASCADE | 租户 ID（FK CASCADE） |
| `session_id` | VARCHAR(36) | NOT NULL | 会话 ID |
| `assistant_message_id` | VARCHAR(36) | NOT NULL | 关联助手消息 ID |
| `agent_id` | VARCHAR(36) | NOT NULL DEFAULT '' | Agent ID |
| `agent_tenant_id` | INTEGER | NOT NULL DEFAULT 0 | Agent 租户 ID |
| `placement` | VARCHAR(32) | NOT NULL | 插入位置 |
| `config_hash` | VARCHAR(64) | NOT NULL | 生成配置哈希（缓存键） |
| `locale` | VARCHAR(16) | NOT NULL DEFAULT '' | 语言 |
| `status` | VARCHAR(16) | NOT NULL | 状态 |
| `allow_regenerate` | BOOLEAN | NOT NULL DEFAULT FALSE | 是否允许重新生成 |
| `suppression_reason` | VARCHAR(64) | NOT NULL DEFAULT '' | 抑制原因（不生成时） |
| `questions` | JSONB | NOT NULL DEFAULT '[]'::jsonb | 问题列表（JSONB） |
| `model_id` | VARCHAR(64) | NOT NULL DEFAULT '' | 生成模型 |
| `prompt_tokens` | INTEGER | NOT NULL DEFAULT 0 | 提示词 token 数 |
| `completion_tokens` | INTEGER | NOT NULL DEFAULT 0 | 生成 token 数 |
| `latency_ms` | BIGINT | NOT NULL DEFAULT 0 | 生成耗时（毫秒） |
| `error_code` | VARCHAR(64) | NOT NULL DEFAULT '' | 错误码 |
| `lease_until` | TIMESTAMP WITH TIME ZONE | - | 租约到期（去重） |
| `generated_at` | TIMESTAMP WITH TIME ZONE | - | 生成时间 |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**主键**：`id`

**索引（3）**：`idx_message_suggestion_sets_cache_key(tenant_id, assistant_message_id, placement, config_hash, locale)`、`idx_message_suggestion_sets_session(tenant_id, session_id, created_at DESC)`、`idx_message_suggestion_sets_status(status, lease_until)`

### message_suggestion_events

**用途**：推荐问题点击/展示埋点事件。

**来源**：创建于 `000067_question_suggestions.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PRIMARY KEY | 事件 ID |
| `tenant_id` | INTEGER | NOT NULL REFERENCES tenants(id) ON DELETE CASCADE | 租户 ID（FK CASCADE） |
| `session_id` | VARCHAR(36) | NOT NULL | 会话 ID |
| `suggestion_set_id` | VARCHAR(36) | NOT NULL REFERENCES message_suggestion_sets(id) ON DELETE CASCADE | 推荐问题集 ID（FK CASCADE） |
| `question_id` | VARCHAR(64) | NOT NULL DEFAULT '' | 问题 ID |
| `event_type` | VARCHAR(32) | NOT NULL | 事件类型：shown / clicked 等 |
| `actor_id` | VARCHAR(512) | NOT NULL DEFAULT '' | 行为主体 |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**主键**：`id`

**索引（3）**：`idx_message_suggestion_events_set(suggestion_set_id, created_at)`、`idx_message_suggestion_events_session(tenant_id, session_id, created_at)`、`idx_message_suggestion_events_type(event_type, created_at)`


---

## 五、Agent / MCP

### custom_agents

**用途**：自定义 Agent（GPTs 式），config JSONB 保存完整配置；复合主键 (id, tenant_id) 允许同 id 多租户内置 Agent。

**来源**：创建于 `000006_custom_agents.up.sql`；后续修改：`000043_tenant_rbac.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | NOT NULL DEFAULT uuid_generate_v4() | Agent ID（UUID，与 tenant_id 组成复合主键） |
| `name` | VARCHAR(255) | NOT NULL | Agent 名称 |
| `description` | TEXT | - | 描述 |
| `avatar` | VARCHAR(64) | - | 头像（emoji），默认 🤖 |
| `is_builtin` | BOOLEAN | NOT NULL DEFAULT false | 是否内置 Agent |
| `tenant_id` | INTEGER | NOT NULL | 租户 ID |
| `created_by` | VARCHAR(36) | - | 创建者用户 ID |
| `config` | JSONB | NOT NULL DEFAULT '{}' | Agent 配置（JSONB：agent_mode、system_prompt、模型、工具、检索参数等） |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `runnable_by_viewer` | BOOLEAN | NOT NULL DEFAULT TRUE | 只读成员是否可运行 |


**表级约束**：`PRIMARY KEY (id, tenant_id)`

**索引（3）**：`idx_custom_agents_tenant_id(tenant_id)`、`idx_custom_agents_is_builtin(is_builtin)`、`idx_custom_agents_deleted_at(deleted_at)`

### mcp_services

**用途**：MCP 服务注册（SSE/HTTP/stdio 传输），支持认证、环境变量、内置服务。

**来源**：创建于 `000001_agent.up.sql`；后续修改：`000017_mcp_builtin.up.sql`

> 数据库注释：*MCP service configurations*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY | MCP 服务 ID（UUID） |
| `tenant_id` | INTEGER | NOT NULL | 租户 ID |
| `name` | VARCHAR(255) | NOT NULL | 服务名 |
| `description` | TEXT | - | 描述 |
| `enabled` | BOOLEAN | DEFAULT true | 是否启用 |
| `transport_type` | VARCHAR(50) | NOT NULL | 传输类型：sse / streamable-http / stdio 等 |
| `url` | VARCHAR(512) | - | 服务地址 |
| `headers` | JSONB | - | 请求头（JSONB） |
| `auth_config` | JSONB | - | 认证配置（JSONB） |
| `advanced_config` | JSONB | - | 高级配置（JSONB） |
| `stdio_config` | JSONB | - | stdio 启动配置（JSONB） |
| `env_vars` | JSONB | - | 环境变量（JSONB） |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP | - | 软删除时间 |
| `is_builtin` | BOOLEAN | NOT NULL DEFAULT false | 是否内置服务 |

**主键**：`id`

**索引（4）**：`idx_mcp_services_tenant_id(tenant_id)`、`idx_mcp_services_enabled(enabled)`、`idx_mcp_services_deleted_at(deleted_at)`、`idx_mcp_services_is_builtin(is_builtin)`

### mcp_tool_approvals

**用途**：MCP 工具级审批开关。

**来源**：创建于 `000042_mcp_tool_approval.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY | 审批配置 ID |
| `tenant_id` | INTEGER | NOT NULL | 租户 ID |
| `service_id` | VARCHAR(36) | NOT NULL REFERENCES mcp_services(id) ON DELETE CASCADE | MCP 服务 ID（FK CASCADE） |
| `tool_name` | VARCHAR(512) | NOT NULL | 工具名 |
| `require_approval` | BOOLEAN | NOT NULL DEFAULT false | 是否需要审批 |
| `created_at` | TIMESTAMP | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | NOT NULL DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**主键**：`id`

**索引（2）**：`idx_mcp_tool_approvals_tenant_svc_tool(tenant_id, service_id, tool_name)`、`idx_mcp_tool_approvals_service_id(service_id)`

### mcp_oauth_clients

**用途**：MCP OAuth 客户端注册。

**来源**：创建于 `000062_mcp_oauth.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY | OAuth 客户端配置 ID |
| `tenant_id` | INTEGER | NOT NULL | 租户 ID |
| `service_id` | VARCHAR(36) | NOT NULL REFERENCES mcp_services(id) ON DELETE CASCADE | MCP 服务 ID（FK CASCADE） |
| `client_id` | VARCHAR(512) | NOT NULL | OAuth Client ID |
| `client_secret` | TEXT | - | OAuth Client Secret |
| `redirect_uri` | VARCHAR(1024) | - | 回调地址 |
| `created_at` | TIMESTAMP | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | NOT NULL DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**主键**：`id`

**索引（2）**：`idx_mcp_oauth_clients_tenant_svc(tenant_id, service_id)`、`idx_mcp_oauth_clients_service_id(service_id)`

### mcp_oauth_tokens

**用途**：MCP OAuth 用户授权令牌（principal 模型，刷新租约防并发）。

**来源**：创建于 `000062_mcp_oauth.up.sql`；后续修改：`000064_principal_model.up.sql`, `000074_mcp_oauth_refresh_lease.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY | OAuth 令牌 ID |
| `tenant_id` | INTEGER | NOT NULL | 租户 ID |
| `user_id` | VARCHAR(512) | NOT NULL | 用户 ID（兼容旧数据） |
| `service_id` | VARCHAR(36) | NOT NULL REFERENCES mcp_services(id) ON DELETE CASCADE | MCP 服务 ID（FK CASCADE） |
| `access_token` | TEXT | - | 访问令牌 |
| `refresh_token` | TEXT | - | 刷新令牌 |
| `token_type` | VARCHAR(32) | - | 令牌类型 |
| `expires_at` | TIMESTAMP | - | 过期时间 |
| `created_at` | TIMESTAMP | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | NOT NULL DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `principal_type` | VARCHAR(32) | - | 主体类型：web_user 等 |
| `principal_id` | VARCHAR(512) | - | 主体 ID |
| `refresh_lease_id` | VARCHAR(36) | - | 刷新租约 ID（防并发刷新） |
| `refresh_lease_until` | TIMESTAMP WITH TIME ZONE | - | 刷新租约到期时间 |

**主键**：`id`

**索引（5）**：`idx_mcp_oauth_tokens_tenant_user_svc(tenant_id, user_id, service_id)`、`idx_mcp_oauth_tokens_service_id(service_id)`、`idx_mcp_oauth_tokens_user_id(user_id)`、`idx_mcp_oauth_tokens_tenant_principal_svc(tenant_id, principal_type, principal_id, service_id)`、`idx_mcp_oauth_tokens_principal(principal_type, principal_id)`

### web_search_providers

**用途**：Web 搜索提供商配置（Bing/Serper/Tavily 等）。

**来源**：创建于 `000030_web_search_providers.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | NOT NULL PRIMARY KEY | 搜索 Provider 配置 ID |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `name` | VARCHAR(255) | NOT NULL | 配置名 |
| `provider` | VARCHAR(50) | NOT NULL | 提供商：bing / serper / tavily 等 |
| `description` | TEXT | - | 描述 |
| `parameters` | JSONB | - | 参数（JSONB） |
| `is_default` | BOOLEAN | DEFAULT false | 是否默认 |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP | NULL | 软删除时间 |

**主键**：`id`

**索引（3）**：`idx_web_search_providers_tenant_id(tenant_id)`、`idx_web_search_providers_provider(provider)`、`idx_web_search_providers_deleted_at(deleted_at)`


---

## 六、IM 接入 / 嵌入渠道

### im_channel_sessions

**用途**：IM 平台会话 ↔ 内部 session 映射（企微/钉钉/飞书等）。

**来源**：创建于 `000021_im_channel.up.sql`；后续修改：`000021_im_channel.up.sql`, `000028_im_thread_session.up.sql`

> 数据库注释：*Maps IM platform channels to WeKnora conversation sessions*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 会话映射 ID |
| `platform` | VARCHAR(20) | NOT NULL | IM 平台：wecom / dingtalk / feishu / lark 等 *IM platform identifier: wecom, feishu, etc.* |
| `user_id` | VARCHAR(128) | NOT NULL | 平台用户 ID *Platform-specific user identifier* |
| `chat_id` | VARCHAR(128) | NOT NULL DEFAULT '' | 平台会话 ID *Platform-specific chat/group identifier, empty for direct messages* |
| `session_id` | VARCHAR(36) | NOT NULL REFERENCES sessions(id) ON DELETE CASCADE | 内部会话 ID（FK sessions.id CASCADE） *Associated WeKnora session ID* |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID *Tenant that owns this channel mapping* |
| `agent_id` | VARCHAR(36) | DEFAULT '' | Agent ID *Custom agent ID used for this channel, empty for default* |
| `status` | VARCHAR(20) | NOT NULL DEFAULT 'active' | 状态：active / inactive *Channel status: active, paused, expired* |
| `metadata` | JSONB | DEFAULT '{}' | 元数据（JSONB） *Platform-specific extra data (JSON)* |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `im_channel_id` | VARCHAR(36) | DEFAULT '' | IM 渠道 ID（im_channels.id） |
| `thread_id` | VARCHAR(128) | NOT NULL DEFAULT '' | 平台线程 ID（群聊线程） *Platform thread identifier for thread-based sessions. Empty for user-mode sessions.* |

**主键**：`id`

**索引（8）**：`idx_channel_lookup(platform, user_id, chat_id, tenant_id)`、`idx_im_channel_tenant(tenant_id)`、`idx_im_channel_session(session_id)`、`idx_im_channel_deleted(deleted_at)`、`idx_im_channel_sessions_channel(im_channel_id)`、`idx_channel_thread_lookup(platform, chat_id, thread_id, tenant_id)`、`idx_channel_lookup(platform, user_id, chat_id, tenant_id, agent_id)`、`idx_channel_thread_lookup(platform, chat_id, thread_id, tenant_id, agent_id)`

### im_channels

**用途**：IM 渠道配置（平台凭据、绑定 Agent/KB）。

**来源**：创建于 `000021_im_channel.up.sql`；后续修改：`000023_im_channel_kb_id.up.sql`, `000024_im_channel_bot_identity.up.sql`, `000028_im_thread_session.up.sql`

> 数据库注释：*IM platform channel configurations bound to agents*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | IM 渠道 ID |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `agent_id` | VARCHAR(36) | NOT NULL | 绑定的 Agent ID *Agent ID this channel is bound to* |
| `platform` | VARCHAR(20) | NOT NULL | IM 平台 *IM platform: wecom, feishu* |
| `name` | VARCHAR(255) | NOT NULL DEFAULT '' | 渠道名 *User-defined channel name for identification* |
| `enabled` | BOOLEAN | NOT NULL DEFAULT true | 是否启用 |
| `mode` | VARCHAR(20) | NOT NULL DEFAULT 'websocket' | 接入模式：websocket / webhook 等 *Connection mode: webhook or websocket* |
| `output_mode` | VARCHAR(20) | NOT NULL DEFAULT 'stream' | 输出模式：stream / reply 等 *Output mode: stream (real-time) or full (wait for complete answer)* |
| `credentials` | JSONB | NOT NULL DEFAULT '{}' | 平台凭据（JSONB） *Platform credentials (JSONB): WeCom webhook={corp_id,agent_secret,token,encoding_aes_key,corp_agent_id}, WeCom ws={bot_id,bot_secret}, Feishu={app_id,app_secret,verification_token,encrypt_key}* |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `knowledge_base_id` | VARCHAR(36) | DEFAULT '' | 绑定知识库 ID（默认） |
| `bot_identity` | VARCHAR(255) | NOT NULL DEFAULT '' | 机器人身份标识 *Unique bot identity derived from credentials (e.g. wecom:ws:{bot_id}, feishu:{app_id}). Used to prevent duplicate bot bindings.* |
| `session_mode` | VARCHAR(20) | NOT NULL DEFAULT 'user' | 会话模式：user / chat / group 等 *Session resolution mode: user (per user+chat, default) or thread (per thread)* |

**主键**：`id`

**索引（4）**：`idx_im_channels_tenant(tenant_id)`、`idx_im_channels_agent(agent_id)`、`idx_im_channels_deleted(deleted_at)`、`idx_im_channels_bot_identity(bot_identity)`

### embed_channels

**用途**：公开嵌入渠道（网页挂件，发布令牌 + 限流 + 主题定制）。

**来源**：创建于 `000060_embed_channels.up.sql`

> 数据库注释：*Web embed channels for publishing agent chat to external sites via iframe*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 嵌入式渠道 ID |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `agent_id` | VARCHAR(36) | NOT NULL DEFAULT 'builtin-quick-answer' | 绑定 Agent ID（默认 builtin-quick-answer） |
| `name` | VARCHAR(255) | NOT NULL DEFAULT '' | 渠道名 |
| `enabled` | BOOLEAN | NOT NULL DEFAULT true | 是否启用 |
| `publish_token` | VARCHAR(64) | NOT NULL DEFAULT '' | 发布令牌（网页身份验证） *Plaintext scoped token (em_ prefix); rotatable from management UI* |
| `allowed_origins` | JSONB | NOT NULL DEFAULT '[]' | 允许的跨域来源（JSONB） *JSON array of allowed HTTP(S) origins for embed API requests; empty rejects all (management UI requires at least one)* |
| `welcome_message` | TEXT | NOT NULL DEFAULT '' | 欢迎语 |
| `rate_limit_per_minute` | INTEGER | NOT NULL DEFAULT 30 | 每分钟限流（默认 30） *Per-IP per-minute request cap for the public embed endpoints* |
| `rate_limit_per_day` | INTEGER | NOT NULL DEFAULT 10000 | 每日限流（默认 10000） *Channel-wide daily total request cap across all IPs; bounds cost/abuse since the publish token is publicly visible* |
| `primary_color` | VARCHAR(32) | NOT NULL DEFAULT '' | 主题色 *CSS color for embed widget accent (e.g. #0052d9)* |
| `page_title` | VARCHAR(255) | NOT NULL DEFAULT '' | 页面标题 *Browser tab title for the embed page* |
| `header_title_mode` | VARCHAR(32) | NOT NULL DEFAULT 'channel' | 头部标题模式：channel / caption 等 *Embed header title source: channel (fixed page title) or session (auto-generated after first message)* |
| `show_suggested_questions` | BOOLEAN | NOT NULL DEFAULT true | 是否显示推荐问题 *When true, embed chat shows suggested starter questions before the first visitor message* |
| `widget_position` | VARCHAR(32) | NOT NULL DEFAULT 'bottom-right' | 悬浮位置：bottom-right / bottom-left / top-right / top-left *Floating widget corner: bottom-right, bottom-left, top-right, top-left* |
| `allow_web_search` | BOOLEAN | NOT NULL DEFAULT false | 是否允许 Web 搜索 *When true, embed chat may show web search toggle; visitor must opt in per message* |
| `allow_memory` | BOOLEAN | NOT NULL DEFAULT false | 是否允许记忆 *When true, embed chat may use agent memory; client cannot override when false* |
| `allow_file_upload` | BOOLEAN | NOT NULL DEFAULT false | 是否允许上传文件 *When true, embed chat may send images; client cannot override when false* |
| `default_locale` | VARCHAR(16) | NOT NULL DEFAULT '' | 默认语言 *Default visitor UI locale (zh-CN, en-US, ko-KR, ru-RU); empty follows browser* |
| `webhook_url` | VARCHAR(512) | NOT NULL DEFAULT '' | Webhook 地址 *HTTPS endpoint for outbound message_sent / message_received events* |
| `webhook_secret` | VARCHAR(128) | NOT NULL DEFAULT '' | Webhook 密钥 *Optional HMAC-SHA256 secret for X-WeKnora-Signature header* |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |

**主键**：`id`

**索引（4）**：`idx_embed_channels_tenant(tenant_id)`、`idx_embed_channels_agent(agent_id)`、`idx_embed_channels_publish_token(publish_token)`、`idx_embed_channels_deleted(deleted_at)`


---

## 七、组织协作 / 内容分享

### organizations

**用途**：跨租户协作空间（共享空间），通过邀请码/审批加入。

**来源**：创建于 `000012_organizations.up.sql`；后续修改：`000046_org_owner_tenant_id.up.sql`

> 数据库注释：*Organizations for cross-tenant collaboration*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 组织（共享空间）ID |
| `name` | VARCHAR(255) | NOT NULL | 组织名 |
| `description` | TEXT | - | 描述 |
| `owner_id` | VARCHAR(36) | NOT NULL | 所有者用户 ID *User ID of the organization owner* |
| `invite_code` | VARCHAR(32) | - | 邀请码（唯一） *Unique invitation code for joining the organization* |
| `require_approval` | BOOLEAN | DEFAULT FALSE | 加入是否需要管理员审批 *Whether joining this organization requires admin approval* |
| `invite_code_expires_at` | TIMESTAMP WITH TIME ZONE | - | 邀请码过期时间 *When the current invite code expires; NULL means no expiry (legacy)* |
| `invite_code_validity_days` | SMALLINT | NOT NULL DEFAULT 7 | 邀请链接有效期（天）：0=永久 *Invite link validity in days: 0=never expire, 1/7/30 days* |
| `avatar` | VARCHAR(512) | DEFAULT '' | 头像 |
| `searchable` | BOOLEAN | NOT NULL DEFAULT FALSE | 是否可被搜索加入 *When true, space appears in search and can be joined by org ID* |
| `member_limit` | INTEGER | NOT NULL DEFAULT 50 | 成员上限（0=不限制） *Max members allowed; 0 means no limit* |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `owner_tenant_id` | BIGINT | - | 所有者主租户 ID *Plan 3 (#1303): owning tenant; cannot be removed/downgraded from OTM.* |

**主键**：`id`

**索引（4）**：`idx_organizations_invite_code(invite_code)`、`idx_organizations_owner_id(owner_id)`、`idx_organizations_deleted_at(deleted_at)`、`idx_organizations_owner_tenant(owner_tenant_id)`

### organization_members

**用途**：组织成员（用户粒度）与角色。

**来源**：创建于 `000012_organizations.up.sql`；后续修改：`000045_org_tenant_members.up.sql`

> 数据库注释：*Members of organizations with their roles*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 成员记录 ID |
| `organization_id` | VARCHAR(36) | NOT NULL REFERENCES organizations(id) ON DELETE CASCADE | 组织 ID（FK CASCADE） |
| `user_id` | VARCHAR(36) | NOT NULL | 用户 ID |
| `tenant_id` | INTEGER | NOT NULL | 成员所属租户 ID *The tenant ID that the member belongs to* |
| `role` | VARCHAR(32) | NOT NULL DEFAULT 'viewer' | 角色：admin / editor / viewer *Member role: admin, editor, or viewer* |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**主键**：`id`

**索引（4）**：`idx_org_members_org_user(organization_id, user_id)`、`idx_org_members_user_id(user_id)`、`idx_org_members_tenant_id(tenant_id)`、`idx_org_members_role(role)`

### organization_tenant_members

**用途**：组织-租户粒度的成员关系（跨租户协作）。

**来源**：创建于 `000045_org_tenant_members.up.sql`

> 数据库注释：*Plan 3: Tenants (not users) are organization members.*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 组织-租户成员关系 ID |
| `organization_id` | VARCHAR(36) | NOT NULL REFERENCES organizations(id) ON DELETE CASCADE | 组织 ID（FK CASCADE） |
| `tenant_id` | INTEGER | NOT NULL | 租户 ID |
| `role` | VARCHAR(32) | NOT NULL DEFAULT 'viewer' | 角色 *Tenant role inside the org: admin | editor | viewer.* |
| `representative_user_id` | VARCHAR(36) | NOT NULL DEFAULT '' | 代表用户 ID *Display-only: the user who first brought this tenant into the org.* |
| `joined_at` | TIMESTAMP WITH TIME ZONE | - | 加入时间 |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**主键**：`id`

**索引（3）**：`idx_org_tenant_members_unique(organization_id, tenant_id)`、`idx_org_tenant_members_by_tenant(tenant_id)`、`idx_org_tenant_members_role(organization_id, role)`

### organization_join_requests

**用途**：加入/升级角色的审批流。

**来源**：创建于 `000012_organizations.up.sql`

> 数据库注释：*Join requests for organizations that require approval*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 申请记录 ID |
| `organization_id` | VARCHAR(36) | NOT NULL REFERENCES organizations(id) ON DELETE CASCADE | 组织 ID（FK CASCADE） |
| `user_id` | VARCHAR(36) | NOT NULL | 申请用户 ID |
| `tenant_id` | INTEGER | NOT NULL | 用户租户 ID |
| `status` | VARCHAR(32) | NOT NULL DEFAULT 'pending' | 状态：pending / approved / rejected *Request status: pending, approved, rejected* |
| `requested_role` | VARCHAR(32) | NOT NULL DEFAULT 'viewer' | 申请角色 *Role requested by the applicant: admin, editor, viewer* |
| `request_type` | VARCHAR(32) | NOT NULL DEFAULT 'join' | 类型：join（加入）/ upgrade（升级角色） *join for new member, upgrade for role upgrade* |
| `prev_role` | VARCHAR(32) | - | 原角色（升级时） |
| `message` | TEXT | - | 申请留言 *Optional message from the requester* |
| `reviewed_by` | VARCHAR(36) | - | 审批管理员 ID *User ID of the admin who reviewed the request* |
| `reviewed_at` | TIMESTAMP WITH TIME ZONE | - | 审批时间 |
| `review_message` | TEXT | - | 审批意见 *Optional message from the reviewer* |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**主键**：`id`

**索引（6）**：`idx_org_join_requests_org_user_pending(organization_id, user_id)`、`idx_org_join_requests_org_id(organization_id)`、`idx_org_join_requests_user_id(user_id)`、`idx_org_join_requests_status(status)`、`idx_org_join_requests_type(request_type)`、`uq_org_join_requests_pending_per_tenant(organization_id, tenant_id, request_type)`

### kb_shares

**用途**：知识库→组织分享，跨租户访问（source_tenant_id 记录源）。

**来源**：创建于 `000012_organizations.up.sql`

> 数据库注释：*Knowledge base sharing records to organizations*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 分享记录 ID |
| `knowledge_base_id` | VARCHAR(36) | NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE | 被分享的知识库 ID（FK CASCADE） |
| `organization_id` | VARCHAR(36) | NOT NULL REFERENCES organizations(id) ON DELETE CASCADE | 目标组织 ID（FK CASCADE） |
| `shared_by_user_id` | VARCHAR(36) | NOT NULL | 分享者用户 ID |
| `source_tenant_id` | INTEGER | NOT NULL | 知识库源租户 ID *Original tenant ID of the knowledge base for cross-tenant embedding model access* |
| `permission` | VARCHAR(32) | NOT NULL DEFAULT 'viewer' | 权限：admin / editor / viewer *Access permission level: admin, editor, or viewer* |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |

**主键**：`id`

**索引（5）**：`idx_kb_shares_kb_org(knowledge_base_id, organization_id)`、`idx_kb_shares_kb_id(knowledge_base_id)`、`idx_kb_shares_org_id(organization_id)`、`idx_kb_shares_source_tenant(source_tenant_id)`、`idx_kb_shares_deleted_at(deleted_at)`

### agent_shares

**用途**：自定义 Agent→组织分享。

**来源**：创建于 `000012_organizations.up.sql`

> 数据库注释：*Custom agent sharing records to organizations*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY DEFAULT uuid_generate_v4() | 分享记录 ID |
| `agent_id` | VARCHAR(36) | NOT NULL | 被分享的 Agent ID |
| `organization_id` | VARCHAR(36) | NOT NULL REFERENCES organizations(id) ON DELETE CASCADE | 目标组织 ID（FK CASCADE） |
| `shared_by_user_id` | VARCHAR(36) | NOT NULL | 分享者 |
| `source_tenant_id` | INTEGER | NOT NULL | Agent 源租户 ID *Original tenant ID of the agent* |
| `permission` | VARCHAR(32) | NOT NULL DEFAULT 'viewer' | 权限：viewer / editor *Access permission: viewer or editor* |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |

**主键**：`id`

**表级约束**：`FOREIGN KEY (agent_id, source_tenant_id) REFERENCES custom_agents(id, tenant_id) ON DELETE CASCADE`

**索引（5）**：`idx_agent_shares_agent_org(agent_id, source_tenant_id, organization_id)`、`idx_agent_shares_agent_id(agent_id)`、`idx_agent_shares_org_id(organization_id)`、`idx_agent_shares_source_tenant(source_tenant_id)`、`idx_agent_shares_deleted_at(deleted_at)`

### tenant_disabled_shared_agents

**用途**：租户级禁用共享 Agent 名单。

**来源**：创建于 `000012_organizations.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `agent_id` | VARCHAR(36) | NOT NULL | Agent ID |
| `source_tenant_id` | BIGINT | NOT NULL | 源租户 ID |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |


**表级约束**：`PRIMARY KEY (tenant_id, agent_id, source_tenant_id)`

**索引（1）**：`idx_tenant_disabled_shared_agents_tenant_id(tenant_id)`


---

## 八、Wiki 知识整理

### wiki_pages

**用途**：Wiki 页面（知识整理产物），含目录归属、双向链接、来源引用，多页面类型。

**来源**：创建于 `000037_wiki_and_indexing.up.sql`；后续修改：`000061_wiki_page_hierarchy.up.sql`, `000075_wiki_page_revisions.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY | Wiki 页面 ID |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `knowledge_base_id` | VARCHAR(36) | NOT NULL | 知识库 ID |
| `slug` | VARCHAR(255) | NOT NULL | 页面 slug（库内唯一路径） |
| `title` | VARCHAR(512) | NOT NULL DEFAULT '' | 标题 |
| `page_type` | VARCHAR(32) | NOT NULL DEFAULT 'summary' | 页面类型：summary / entity / concept / log（已废弃）等 |
| `status` | VARCHAR(32) | NOT NULL DEFAULT 'published' | 状态：published / draft / archived |
| `content` | TEXT | NOT NULL DEFAULT '' | Markdown 内容 |
| `summary` | TEXT | NOT NULL DEFAULT '' | 摘要 |
| `parent_slug` | VARCHAR(255) | NOT NULL DEFAULT '' | 父页面 slug |
| `folder_id` | VARCHAR(36) | NOT NULL DEFAULT '' | 所在目录 ID（wiki_folders.id，空=根） |
| `category_path` | JSONB | DEFAULT '[]'::JSONB | 目录链（JSONB 数组） |
| `wiki_path` | VARCHAR(1024) | NOT NULL DEFAULT '' | 物化路径（如 /目录/子目录/页面） |
| `depth` | INT | NOT NULL DEFAULT 0 | 目录深度 |
| `sort_order` | INT | NOT NULL DEFAULT 0 | 排序 |
| `source_refs` | JSONB | DEFAULT '[]'::JSONB | 来源引用（JSONB） |
| `chunk_refs` | JSONB | DEFAULT '[]'::JSONB | 引用块（JSONB） |
| `in_links` | JSONB | DEFAULT '[]'::JSONB | 入链（JSONB） |
| `out_links` | JSONB | DEFAULT '[]'::JSONB | 出链（JSONB） |
| `page_metadata` | JSONB | DEFAULT '{}'::JSONB | 页面元数据（JSONB） |
| `aliases` | JSONB | DEFAULT '[]'::JSONB | 别名（JSONB） |
| `version` | INT | NOT NULL DEFAULT 1 | 当前版本号 |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT NOW() | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT NOW() | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |
| `last_edit_source` | VARCHAR(16) | NOT NULL DEFAULT '' | 最近编辑来源：user / wiki / api 等 *Author kind of the current version: pipeline | agent | user | revert ('' = legacy, treated as pipeline)* |
| `last_editor_id` | VARCHAR(64) | NOT NULL DEFAULT '' | 最近编辑者 ID *User id of the caller that produced the current version (empty for background pipeline writes)* |

**主键**：`id`

**索引（9）**：`idx_wiki_pages_kb_slug(knowledge_base_id, slug)`、`idx_wiki_pages_kb_id(knowledge_base_id)`、`idx_wiki_pages_page_type(knowledge_base_id, page_type)`、`idx_wiki_pages_parent_slug(knowledge_base_id, parent_slug)`、`idx_wiki_pages_tree(knowledge_base_id, page_type, wiki_path, sort_order, title)`、`idx_wiki_pages_folder(knowledge_base_id, folder_id)`、`idx_wiki_pages_tenant_id(tenant_id)`、`idx_wiki_pages_deleted_at(deleted_at)`、`idx_wiki_pages_folder_id(folder_id)`

### wiki_folders

**用途**：Wiki 目录树（邻接表），页面 folder_id 归属。

**来源**：创建于 `000037_wiki_and_indexing.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY | 目录 ID |
| `tenant_id` | BIGINT | NOT NULL DEFAULT 0 | 租户 ID |
| `knowledge_base_id` | VARCHAR(36) | NOT NULL | 知识库 ID |
| `parent_id` | VARCHAR(36) | NOT NULL DEFAULT '' | 父目录 ID（空=根） |
| `name` | VARCHAR(255) | NOT NULL | 目录名 |
| `path` | VARCHAR(1024) | NOT NULL DEFAULT '' | 物化路径（/ 连接名称链） |
| `depth` | INT | NOT NULL DEFAULT 0 | 深度 |
| `sort_order` | INT | NOT NULL DEFAULT 0 | 排序 |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT NOW() | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT NOW() | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |

**主键**：`id`

**索引（3）**：`idx_wiki_folders_parent_name(knowledge_base_id, parent_id, name)`、`idx_wiki_folders_parent(knowledge_base_id, parent_id)`、`idx_wiki_folders_deleted_at(deleted_at)`

### wiki_page_issues

**用途**：Wiki 页面质量问题上报（缺信息/错误等）。

**来源**：创建于 `000037_wiki_and_indexing.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY | 问题报告 ID |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `knowledge_base_id` | VARCHAR(36) | NOT NULL | 知识库 ID |
| `slug` | VARCHAR(255) | NOT NULL | 页面 slug |
| `issue_type` | VARCHAR(50) | NOT NULL | 问题类型：content-error / missing-info 等 |
| `description` | TEXT | NOT NULL | 问题描述 |
| `suspected_knowledge_ids` | JSONB | - | 疑似相关知识 ID（JSONB） |
| `status` | VARCHAR(20) | DEFAULT 'pending' NOT NULL | 状态：pending / resolved |
| `reported_by` | VARCHAR(100) | NOT NULL | 报告人标识 |
| `created_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP WITH TIME ZONE | - | 软删除时间 |

**主键**：`id`

**索引（4）**：`idx_wiki_page_issues_tenant_id(tenant_id)`、`idx_wiki_page_issues_knowledge_base_id(knowledge_base_id)`、`idx_wiki_page_issues_slug(slug)`、`idx_wiki_page_issues_status(status)`

### wiki_page_revisions

**用途**：Wiki 页面版本历史。

**来源**：创建于 `000075_wiki_page_revisions.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | PRIMARY KEY | 修订 ID |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `knowledge_base_id` | VARCHAR(36) | NOT NULL | 知识库 ID |
| `page_id` | VARCHAR(36) | NOT NULL | 页面 ID |
| `slug` | VARCHAR(255) | NOT NULL | 页面 slug |
| `version` | INT | NOT NULL | 版本号 |
| `title` | VARCHAR(512) | NOT NULL DEFAULT '' | 标题 |
| `page_type` | VARCHAR(32) | NOT NULL DEFAULT 'summary' | 页面类型 |
| `status` | VARCHAR(32) | NOT NULL DEFAULT 'published' | 状态 |
| `content` | TEXT | NOT NULL DEFAULT '' | 内容 |
| `summary` | TEXT | NOT NULL DEFAULT '' | 摘要 |
| `aliases` | JSONB | DEFAULT '[]'::JSONB | 别名（JSONB） |
| `edit_source` | VARCHAR(16) | NOT NULL DEFAULT '' | 编辑来源：user / wiki / api |
| `editor_id` | VARCHAR(64) | NOT NULL DEFAULT '' | 编辑者 ID |
| `edited_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT NOW() | 编辑时间 |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT NOW() | 创建时间 |

**主键**：`id`

**索引（2）**：`idx_wiki_page_revisions_page_version(page_id, version)`、`idx_wiki_page_revisions_kb_slug(knowledge_base_id, slug)`


---

## 九、数据源同步

### data_sources

**用途**：外部数据源（webhook/api/db）定时同步到知识库。

**来源**：创建于 `000029_datasource_tables.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | NOT NULL PRIMARY KEY | 数据源 ID |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `knowledge_base_id` | VARCHAR(36) | NOT NULL | 目标知识库 ID |
| `name` | VARCHAR(255) | NOT NULL | 数据源名 |
| `type` | VARCHAR(50) | NOT NULL | 类型：webhook / api / database / file 等 |
| `config` | JSONB | - | 连接配置（JSONB） |
| `sync_schedule` | VARCHAR(100) | - | 同步计划（cron） |
| `sync_mode` | VARCHAR(20) | DEFAULT 'incremental' | 同步模式：full / incremental |
| `status` | VARCHAR(32) | DEFAULT 'active' | 状态：active / paused 等 |
| `conflict_strategy` | VARCHAR(32) | DEFAULT 'overwrite' | 冲突策略：overwrite / skip 等 |
| `sync_deletions` | BOOLEAN | DEFAULT true | 是否同步删除 |
| `last_sync_at` | TIMESTAMP | NULL | 最近同步时间 |
| `last_sync_cursor` | JSONB | - | 增量游标（JSONB） |
| `last_sync_result` | JSONB | - | 最近同步结果（JSONB） |
| `error_message` | TEXT | - | 错误信息 |
| `sync_log_retention_days` | INT | DEFAULT 30 | 同步日志保留天数（默认 30） |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP | NULL | 软删除时间 |

**主键**：`id`

**索引（5）**：`idx_data_sources_tenant_id(tenant_id)`、`idx_data_sources_knowledge_base_id(knowledge_base_id)`、`idx_data_sources_type(type)`、`idx_data_sources_status(status)`、`idx_data_sources_deleted_at(deleted_at)`

### sync_logs

**用途**：数据源同步执行日志与统计。

**来源**：创建于 `000029_datasource_tables.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | NOT NULL PRIMARY KEY | 同步日志 ID |
| `data_source_id` | VARCHAR(36) | NOT NULL REFERENCES data_sources(id) ON DELETE CASCADE | 数据源 ID（FK CASCADE） |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `status` | VARCHAR(32) | NOT NULL | 状态：running / success / failed |
| `started_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 开始时间 |
| `finished_at` | TIMESTAMP | NULL | 结束时间 |
| `items_total` | INT | DEFAULT 0 | 总数 |
| `items_created` | INT | DEFAULT 0 | 新建数 |
| `items_updated` | INT | DEFAULT 0 | 更新数 |
| `items_deleted` | INT | DEFAULT 0 | 删除数 |
| `items_skipped` | INT | DEFAULT 0 | 跳过数 |
| `items_failed` | INT | DEFAULT 0 | 失败数 |
| `error_message` | TEXT | - | 错误信息 |
| `result` | JSONB | - | 结果（JSONB） |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**主键**：`id`

**索引（4）**：`idx_sync_logs_data_source_id(data_source_id)`、`idx_sync_logs_tenant_id(tenant_id)`、`idx_sync_logs_status(status)`、`idx_sync_logs_started_at(started_at)`


---

## 十、存储与资源

### storage_backends

**用途**：统一存储后端注册（local/minio/cos），供文档与资源使用。

**来源**：创建于 `000068_storage_backends.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | NOT NULL PRIMARY KEY | 存储后端 ID |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `name` | VARCHAR(255) | NOT NULL | 名称 |
| `provider` | VARCHAR(32) | NOT NULL | 提供方：local / minio / cos 等 |
| `config` | JSONB | NOT NULL DEFAULT '{}' | 配置（JSONB） |
| `source` | VARCHAR(16) | NOT NULL DEFAULT 'user' | 来源：user / system 等 |
| `status` | VARCHAR(16) | NOT NULL DEFAULT 'active' | 状态：active / disabled |
| `legacy_alias` | BOOLEAN | NOT NULL DEFAULT FALSE | 是否为历史别名 |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP | NULL | 软删除时间 |

**主键**：`id`

**索引（3）**：`idx_storage_backends_name_tenant(tenant_id, name)`、`idx_storage_backends_legacy_alias(tenant_id, provider)`、`idx_storage_backends_tenant(tenant_id)`

### resources

**用途**：对象资源注册表（文件/图像），handle 短链接标识，多生命周期。

**来源**：创建于 `000069_resource_registry.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | NOT NULL PRIMARY KEY | 资源 ID |
| `handle` | VARCHAR(22) | NOT NULL UNIQUE | 短句柄（22 字符，唯一，URL 标识） |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `storage_backend_id` | VARCHAR(36) | - | 存储后端 ID |
| `provider` | VARCHAR(32) | NOT NULL | 提供方 |
| `physical_path` | TEXT | NOT NULL | 物理路径 |
| `location_hash` | VARCHAR(64) | NOT NULL | 位置哈希 |
| `kind` | VARCHAR(32) | NOT NULL DEFAULT 'file' | 类型：file / image 等 |
| `mime_type` | VARCHAR(255) | NOT NULL DEFAULT '' | MIME 类型 |
| `original_name` | VARCHAR(1024) | NOT NULL DEFAULT '' | 原始文件名 |
| `size` | BIGINT | NOT NULL DEFAULT 0 | 大小（字节） |
| `content_hash` | VARCHAR(64) | NOT NULL DEFAULT '' | 内容哈希 |
| `lifecycle` | VARCHAR(16) | NOT NULL DEFAULT 'persistent' | 生命周期：persistent / temporary |
| `expires_at` | TIMESTAMP | NULL | 过期时间（temporary） |
| `state` | VARCHAR(16) | NOT NULL DEFAULT 'active' | 状态：active / deleted |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 更新时间 |
| `deleted_at` | TIMESTAMP | NULL | 软删除时间 |

**主键**：`id`

**索引（3）**：`idx_resources_tenant_location(tenant_id, location_hash)`、`idx_resources_tenant(tenant_id)`、`idx_resources_backend(storage_backend_id)`

### resource_bindings

**用途**：资源与业务实体（知识/会话/消息）的绑定关系。

**来源**：创建于 `000069_resource_registry.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | NOT NULL PRIMARY KEY | 绑定 ID |
| `resource_id` | VARCHAR(36) | NOT NULL REFERENCES resources(id) ON DELETE CASCADE | 资源 ID（FK CASCADE） |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `owner_type` | VARCHAR(32) | NOT NULL | 所有者类型：knowledge / session / message 等 |
| `owner_id` | VARCHAR(64) | NOT NULL | 所有者 ID |
| `relation` | VARCHAR(32) | NOT NULL DEFAULT 'attachment' | 关系：attachment 等 |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**主键**：`id`

**索引（2）**：`idx_resource_bindings_unique(resource_id, owner_type, owner_id, relation)`、`idx_resource_bindings_owner(tenant_id, owner_type, owner_id)`

### resource_access_grants

**用途**：资源限时访问令牌授权（分享链接）。

**来源**：创建于 `000069_resource_registry.up.sql`；后续修改：`000072_auth_timestamp_tz.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | VARCHAR(36) | NOT NULL PRIMARY KEY | 授权记录 ID |
| `token_hash` | VARCHAR(64) | NOT NULL UNIQUE | 访问令牌哈希（唯一） |
| `resource_id` | VARCHAR(36) | NOT NULL REFERENCES resources(id) ON DELETE CASCADE | 资源 ID（FK CASCADE） |
| `access_scope` | VARCHAR(16) | NOT NULL DEFAULT 'read' | 访问范围：read 等 |
| `expires_at` | TIMESTAMP | NOT NULL | 过期时间 |
| `revoked_at` | TIMESTAMP | NULL | 撤销时间 |
| `created_at` | TIMESTAMP | DEFAULT CURRENT_TIMESTAMP | 创建时间 |

**主键**：`id`

**索引（2）**：`idx_resource_access_grants_resource(resource_id)`、`idx_resource_access_grants_expires(expires_at)`


---

## 十一、任务队列 / 处理追踪

### task_pending_ops

**用途**：去重任务队列（wiki 批量摄取等），支持认领与失败计数。

**来源**：创建于 `000041_task_queue_and_wiki_indexes.up.sql`

> 数据库注释：*Generic durable pending-op queue keyed by (task_type, scope, scope_id). Replaces ad-hoc Redis-list queues that were vulnerable to TTL eviction.*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PRIMARY KEY | 任务 ID（自增） |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `task_type` | VARCHAR(64) | NOT NULL | 任务类型（如 wiki:ingest） *Free-form task identifier, e.g. "wiki:ingest" — should match an asynq task type when applicable.* |
| `scope` | VARCHAR(32) | NOT NULL | 作用域类型：knowledge_base / knowledge / tenant *Logical scope, e.g. "knowledge_base" / "knowledge" / "tenant". Read together with scope_id.* |
| `scope_id` | VARCHAR(64) | NOT NULL | 作用域 ID |
| `op` | VARCHAR(32) | NOT NULL | 操作名 |
| `dedup_key` | VARCHAR(128) | NOT NULL DEFAULT '' | 去重键 *Optional service-defined key used by the consumer to de-duplicate equivalent ops within a single batch peek. Empty means no de-dup.* |
| `payload` | JSONB | NOT NULL DEFAULT '{}'::JSONB | 任务载荷（JSONB） |
| `fail_count` | INT | NOT NULL DEFAULT 0 | 失败次数 *In-batch retry counter: the consumer increments it via IncrFailCount and dead-letters once it exceeds a service-defined cap.* |
| `enqueued_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | 入队时间 |
| `claimed_at` | TIMESTAMPTZ | - | 认领时间 *Concurrent-claim marker: set to NOW() when a consumer claims the row (SELECT ... FOR UPDATE SKIP LOCKED). NULL = unclaimed; a value older than the consumer stale threshold is a crashed/abandoned claim and is recoverable. A fresh claim blocks its whole dedup_key so same-document ops never split across concurrent batches.* |

**主键**：`id`

**索引（2）**：`idx_task_pending_ops_scope(task_type, scope, scope_id, id)`、`idx_task_pending_ops_tenant(tenant_id)`

### task_dead_letters

**用途**：任务死信（超限失败的任务载荷留存）。

**来源**：创建于 `000041_task_queue_and_wiki_indexes.up.sql`

> 数据库注释：*Permanent archive of tasks that exhausted retries. Written by the asynq dead-letter middleware and by service-level retry handlers (e.g. wiki ingest per-doc retries).*

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PRIMARY KEY | 死信 ID |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `task_type` | VARCHAR(64) | NOT NULL | 任务类型 |
| `scope` | VARCHAR(32) | NOT NULL | 作用域类型 |
| `scope_id` | VARCHAR(64) | NOT NULL | 作用域 ID |
| `related_id` | VARCHAR(64) | NOT NULL DEFAULT '' | 关联 ID *Optional secondary identifier. Wiki ingest puts knowledge_id here so retract/ingest dead letters cluster around the source document.* |
| `payload` | JSONB | NOT NULL | 载荷（JSONB） *Raw task payload (asynq.Task.Payload) at the time of failure. Allows manual requeue via SQL + asynq.Client.Enqueue.* |
| `last_error` | TEXT | NOT NULL DEFAULT '' | 最后错误 *String form of the error that caused the final retry to fail. Long stack traces are kept verbatim.* |
| `fail_count` | INT | NOT NULL | 失败次数 |
| `failed_at` | TIMESTAMPTZ | NOT NULL DEFAULT NOW() | 失败时间 |

**主键**：`id`

**索引（3）**：`idx_task_dead_letters_scope(scope, scope_id, failed_at DESC)`、`idx_task_dead_letters_tenant(tenant_id, failed_at DESC)`、`idx_task_dead_letters_task_type(task_type, failed_at DESC)`

### knowledge_processing_spans

**用途**：文档处理链路追踪（跨度树：根→阶段→子跨度→生成）。

**来源**：创建于 `000055_knowledge_processing_spans.up.sql`；后续修改：`000066_expand_knowledge_span_name.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `id` | BIGSERIAL | PRIMARY KEY | 处理跨度 ID |
| `knowledge_id` | VARCHAR(64) | NOT NULL | 知识条目 ID |
| `attempt` | INT | NOT NULL DEFAULT 1 | 尝试次数 |
| `span_id` | VARCHAR(64) | NOT NULL | 跨度 ID |
| `parent_span_id` | VARCHAR(64) | - | 父跨度 ID |
| `name` | VARCHAR(255) | NOT NULL | 跨度名（阶段名） |
| `kind` | VARCHAR(16) | NOT NULL | 类型：root / stage / subspan / generation |
| `status` | VARCHAR(16) | NOT NULL | 状态：pending / running / done / failed / skipped / cancelled |
| `input` | JSONB | - | 输入（JSONB） |
| `output` | JSONB | - | 输出（JSONB） |
| `metadata` | JSONB | - | 元数据（JSONB） |
| `error_code` | VARCHAR(64) | - | 错误码 |
| `error_message` | TEXT | - | 错误信息 |
| `error_detail` | TEXT | - | 错误详情 |
| `started_at` | TIMESTAMP WITH TIME ZONE | - | 开始时间 |
| `finished_at` | TIMESTAMP WITH TIME ZONE | - | 结束时间 |
| `duration_ms` | BIGINT | - | 耗时（毫秒） |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 创建时间 |
| `updated_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 更新时间 |

**主键**：`id`

**表级约束**：`CONSTRAINT uq_kpspan_attempt_span UNIQUE (knowledge_id, attempt, span_id)`

**索引（3）**：`idx_kpspan_knowledge_attempt(knowledge_id, attempt)`、`idx_kpspan_status_started(status, started_at)`、`idx_kpspan_parent(parent_span_id)`


---

## 十二、用户个性化

### user_resource_favorites

**用途**：用户收藏（知识库/Agent）。

**来源**：创建于 `000047_user_resource_favorites.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `user_id` | VARCHAR(36) | NOT NULL | 用户 ID |
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `resource_type` | VARCHAR(16) | NOT NULL | 资源类型：kb / agent |
| `resource_id` | VARCHAR(64) | NOT NULL | 资源 ID |
| `created_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 收藏时间 |


**表级约束**：`PRIMARY KEY (user_id, tenant_id, resource_type, resource_id)`

**索引（2）**：`idx_user_resource_favorites_user_tenant_type_created_at(user_id, tenant_id, resource_type, created_at DESC)`、`idx_user_resource_favorites_tenant_id(tenant_id)`

### user_kb_pins

**用途**：用户级知识库置顶。

**来源**：创建于 `000050_user_kb_pins.up.sql`

| 字段 | 类型 | 约束 / 默认值 | 说明 |
|---|---|---|---|
| `tenant_id` | BIGINT | NOT NULL | 租户 ID |
| `user_id` | VARCHAR(36) | NOT NULL | 用户 ID |
| `kb_id` | VARCHAR(36) | NOT NULL | 知识库 ID |
| `pinned_at` | TIMESTAMP WITH TIME ZONE | NOT NULL DEFAULT CURRENT_TIMESTAMP | 置顶时间 |


**表级约束**：`PRIMARY KEY (tenant_id, user_id, kb_id)`

**索引（1）**：`idx_user_kb_pins_user_tenant_pinned_at(tenant_id, user_id, pinned_at DESC)`


---


---

## 约束与外键一览

> 本节从迁移脚本中提取全部**主键、外键、唯一约束、CHECK 约束**。每张表字段表里的"约束/默认值"列已有零散信息，本节是完整汇总。

### 主键

**单列主键（48 张表）**：
`tenants.id`、`models.id`、`knowledge_bases.id`、`knowledges.id`、`sessions.id`、`messages.id`、`chunks.id`、`users.id`、`auth_tokens.id`、`knowledge_tags.id`、`mcp_services.id`、`embeddings.id`、`organizations.id`、`organization_members.id`、`kb_shares.id`、`organization_join_requests.id`、`agent_shares.id`、`im_channel_sessions.id`、`im_channels.id`、`data_sources.id`、`sync_logs.id`、`web_search_providers.id`、`vector_stores.id`、`wiki_pages.id`、`wiki_folders.id`、`wiki_page_issues.id`、`task_pending_ops.id`、`task_dead_letters.id`、`mcp_tool_approvals.id`、`tenant_members.id`、`audit_logs.id`、`organization_tenant_members.id`、`tenant_invitations.id`、`system_settings.id`、`knowledge_processing_spans.id`、`embed_channels.id`、`mcp_oauth_clients.id`、`mcp_oauth_tokens.id`、`tenant_api_keys.id`、`message_suggestion_sets.id`、`message_suggestion_events.id`、`storage_backends.id`、`resources.id`、`resource_bindings.id`、`resource_access_grants.id`、`temporary_documents.id`、`wiki_page_revisions.id`、`chunk_revisions.id`

**复合主键（5 张表）**：

| 表 | 主键列 |
|---|---|
| `custom_agents` | (`id`, `tenant_id`) — 同一 Agent ID 可存在于多个租户（内置 Agent） |
| `tenant_disabled_shared_agents` | (`tenant_id`, `agent_id`, `source_tenant_id`) |
| `user_resource_favorites` | (`user_id`, `tenant_id`, `resource_type`, `resource_id`) |
| `user_kb_pins` | (`tenant_id`, `user_id`, `kb_id`) |
| `knowledge_tag_relations` | (`knowledge_id`, `tag_id`) |

### 外键（20 条）

> 注意：数据库层面外键仅用于**组织/分享、IM 会话、数据源、MCP、消息推荐、资源**等周边表。**核心业务表**（knowledge_bases、knowledges、chunks、sessions、messages、embeddings、wiki_pages 等）**不设物理外键**，关联关系由应用层维护（保证软删除 deleted_at 与跨租户/跨库灵活性）。

| 源表.字段 | 目标表(字段) | ON DELETE | 定义方式 |
|---|---|---|---|
| `organization_members.organization_id` | organizations(id) | CASCADE | 列级 |
| `organization_tenant_members.organization_id` | organizations(id) | CASCADE | 列级 |
| `organization_join_requests.organization_id` | organizations(id) | CASCADE | 列级 |
| `kb_shares.organization_id` | organizations(id) | CASCADE | 列级 |
| `kb_shares.knowledge_base_id` | knowledge_bases(id) | CASCADE | 列级 |
| `agent_shares.organization_id` | organizations(id) | CASCADE | 列级 |
| `agent_shares`(`agent_id`, `source_tenant_id`) | custom_agents(id, tenant_id) | CASCADE | 表级复合外键 |
| `users.tenant_id` | tenants(id) | SET NULL | 约束 fk_users_tenant |
| `auth_tokens.user_id` | users(id) | CASCADE | 约束 fk_auth_tokens_user |
| `im_channel_sessions.session_id` | sessions(id) | CASCADE | 列级 |
| `sync_logs.data_source_id` | data_sources(id) | CASCADE | 列级 |
| `mcp_tool_approvals.service_id` | mcp_services(id) | CASCADE | 列级 |
| `mcp_oauth_clients.service_id` | mcp_services(id) | CASCADE | 列级 |
| `mcp_oauth_tokens.service_id` | mcp_services(id) | CASCADE | 列级 |
| `tenant_api_keys.tenant_id` | tenants(id) | CASCADE | 列级 |
| `message_suggestion_sets.tenant_id` | tenants(id) | CASCADE | 列级 |
| `message_suggestion_events.tenant_id` | tenants(id) | CASCADE | 列级 |
| `message_suggestion_events.suggestion_set_id` | message_suggestion_sets(id) | CASCADE | 列级 |
| `resource_bindings.resource_id` | resources(id) | CASCADE | 列级 |
| `resource_access_grants.resource_id` | resources(id) | CASCADE | 列级 |

### UNIQUE 约束

| 表 | 约束 | 说明 |
|---|---|---|
| `users` | users_username_key (username) | 用户名唯一 |
| `users` | users_email_key (email) | 邮箱唯一 |
| `system_settings` | `key` 列级 UNIQUE | 设置键唯一 |
| `tenant_api_keys` | `key_hash` 列级 UNIQUE | Key 哈希唯一 |
| `resources` | `handle` 列级 UNIQUE | 短句柄唯一 |
| `resource_access_grants` | `token_hash` 列级 UNIQUE | 令牌哈希唯一 |
| `knowledge_processing_spans` | uq_kpspan_attempt_span (knowledge_id, attempt, span_id) | 同一次尝试内 span 唯一 |

另有**部分唯一索引**（等同唯一约束，按条件生效）：`idx_organizations_invite_code`（未删除且 invite_code 非空）、`idx_knowledge_tags_kb_name`（租户+知识库+标签名）、`idx_tenant_invitations_unique_pending`（pending 且 invitee 非空）、`idx_tenant_invitations_token`（token 非空）、`idx_kb_shares_kb_org`、`idx_agent_shares_agent_org`、`idx_mcp_oauth_tokens_tenant_principal_svc`、`idx_chunks_seq_id`、`idx_knowledge_tags_seq_id`、`embeddings_unique_source`(source_id, source_type)、`idx_message_suggestion_sets_cache_key`。

### CHECK 约束

| 表 | 约束 | 规则 |
|---|---|---|
| `im_channels` | chk_im_channels_session_mode | `session_mode` IN ('user', 'thread') |
| `tenant_api_keys` | chk_tenant_api_keys_scope | `scope_type`='tenant' 时 `tenant_id` 非空；`scope_type`='platform' 时 `tenant_id` 为空且 `full_access`=FALSE |

## 核心表关系（ER 摘要）

```
tenants 1─N users / tenant_members / models / knowledge_bases / sessions / custom_agents / mcp_services
users 1─N auth_tokens / organization_members / tenant_members / user_kb_pins
knowledge_bases 1─N knowledges / chunks / knowledge_tags / wiki_pages / data_sources / kb_shares
knowledges 1─N chunks / embeddings / knowledge_processing_spans / knowledge_tag_relations / chunk_revisions
sessions 1─N messages 1─N message_suggestion_sets 1─N message_suggestion_events
custom_agents 1─N sessions / im_channels / embed_channels / agent_shares
organizations 1─N organization_members / kb_shares / agent_shares / organization_join_requests
mcp_services 1─N mcp_tool_approvals / mcp_oauth_clients / mcp_oauth_tokens
vector_stores 1─N knowledge_bases(vector_store_id)
storage_backends 1─N resources / knowledge_bases(storage_backend_id) / tenants(default_storage_backend_id)
resources 1─N resource_bindings / resource_access_grants
wiki_pages 1─N wiki_page_revisions；wiki_folders 1─N wiki_pages(folder_id)
data_sources 1─N sync_logs
```


---

## 迁移与废弃记录

### 已删除的表
| 表 | 删除迁移 | 原因 |
|---|---|---|
| `wiki_log_entries` | 000077_remove_wiki_log | 与知识库活动流功能重复，Wiki 检索不读取 |

### 已删除/迁移的字段
| 表.字段 | 迁移 | 去向 |
|---|---|---|
| `tenants.api_key` | 000065 | 迁入 `tenant_api_keys` 表（加密存储） |
| `knowledges.tag_id` | 000063 | 改为多标签：`knowledge_tag_relations` 关联表 |
| `knowledge_bases.rerank_model_id` | 000001 | 上移至会话级 `sessions.rerank_model_id` |
| `knowledge_bases.vlm_model_id` | 000004 | 并入 `vlm_config` JSONB 字段（model_id） |

### 关键演进时间线
- 000001：用户认证、标签、MCP 服务基础表
- 000002：embeddings 向量表（pgvector + pg_search BM25）
- 000006：custom_agents（GPTs 式自定义智能体）
- 000012：组织共享空间与内容分享（跨租户协作）
- 000021~000028：IM 接入渠道与会话映射
- 000029~000030：数据源同步、Web 搜索提供商
- 000032：外部向量库注册
- 000037、000040、000061、000075：Wiki 体系（页面/目录/问题/修订）
- 000041：去重任务队列（wiki 摄取等）
- 000042~000048：MCP 工具审批、租户 RBAC、审计日志、邀请
- 000053：系统管理员与平台设置
- 000055~000056：文档处理链路追踪（span 树）与 finalizing 状态
- 000062~000064：MCP OAuth（principal 身份模型）
- 000065、000071：租户/平台 API Key 分离
- 000067：推荐问题缓存与埋点
- 000068~000070：统一存储后端、资源注册表、临时文档
- 000075、000078：Wiki 与切块修订历史、块可编辑

---
*本文档由脚本从 migrations/versioned 全部 .up.sql 自动解析生成；字段/索引/注释均来自迁移脚本原文。*
