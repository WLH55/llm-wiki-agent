# 自注册 + 邀请制账户体系

llm_wiki3.0 采用**自注册 + 邀请制并存**的账户体系：

- **自注册**：任何人访问产品 URL → 邮箱+密码注册 → 创建 user 记录 + **自动创建一个自家 tenant**（owner=自己，独占，不可邀请人）。
- **创建 organization**：任何已注册 user 都可以创建 organization（共享空间），创建者是 owner；可创建多个。
- **邀请制加入 organization**：org 的 owner/admin 生成邀请 link（带 token），受邀者打开 link → 已登录则直接加入该 org（默认 viewer 角色，admin 可改）；未登录则先跳注册页，注册后自动加入。
- **多空间归属**：一个 user 可属于 1 个自家 tenant + N 个 organization（被邀请加入的）。
- **workspace context 切换**：登录后必须选择当前 workspace context（自家 tenant / 某 organization），所有 API 调用都带 `X-Workspace-Context` header；无 context 的查询一律 400。

**不做 SSO / LDAP / SAML / OIDC**：v4.2 自部署内网服务场景下自注册已够；企业 SSO 留作未来企业版升级路径。

## Context

PRD v4.2 关于账户体系极度稀薄——只有 US 19（创建 org + 邀请成员）和零散提及"自注册 + 邀请制"。完全没覆盖：

- 第一个用户怎么进来（bootstrap）？
- 自注册流程的细节（邮箱验证？密码强度？）
- 邀请 token 的生命周期（一次性 / 限时 / 可撤回？）
- 多空间归属的 context 切换机制
- 账户停用 / 删除 / 忘记密码

CONTEXT.md 比 PRD 详细——已明确"自注册账户"和"邀请制加入空间"两个术语，但 PRD 没把它写成正式章节。本 ADR 补齐这一层。

## Decision

### 自注册流程

```
1. 用户访问产品 URL → 看到登录页（无账户则点"注册"）
2. 填邮箱 + 密码（强度要求：≥8 位 + 至少一个非字母字符）
3. 后端创建 user 记录（password_hash 用 argon2id）
4. 同事务创建 tenant 记录（owner_id = user.id，name = "{user.email} 的个人空间"）
5. 同事务创建默认 personal space 的 wiki_folders 根节点
6. 返回 session（JWT，24h 有效期；refresh token 7d）
7. 用户登录后默认落到自家 tenant 的 context
```

**邮箱验证**（v4.2 P1 不做，P2 加）：自注册时不强制邮箱验证，但未验证邮箱的用户在创建 organization 数量上受限（默认最多 3 个）。

### 创建 organization

```
任何已登录 user 都可以创建 organization：
1. POST /api/orgs { name, description } → 创建 org 记录（owner_id = caller）
2. 自动把 owner 加入 org_members（role=admin）
3. 创建该 org 的 wiki_folders 根节点（如果 org 要管理文件夹）
```

每个 user 创建 organization 的数量默认上限 10 个（防滥用），可在 admin 后台调整。

### 邀请制加入 organization

```
邀请方（org owner/admin）：
1. POST /api/orgs/{org_id}/invites { email?, role=default_viewer, expires_in=7d }
   - email 可选：填则发邮件；不填则生成裸 link 由邀请方自己转发
2. 系统生成 invite_token（UUID，不可猜），存 org_invites 表
3. 邀请 link: {BASE_URL}/invite/{invite_token}

受邀方：
1. 打开邀请 link
2. GET /api/invites/{token} → 校验 token 有效性 + 返回邀请方信息（哪个 org、谁邀请的、当前角色）
3a. 已登录 → POST /api/invites/{token}/accept → 加入 org_members（role=邀请方指定，默认 viewer）
3b. 未登录 → 跳注册页（带 invite_token 作为 query 参数）→ 注册成功后自动 POST /api/invites/{token}/accept
```

**邀请 token 生命周期**：
- 默认 7 天有效期（admin 可配置 1h~30d）
- 一次性使用（接受后 token 失效）
- 邀请方/admin 可主动撤回（DELETE /api/invites/{token}）
- 同一 org + 同一 email 重复邀请 → 复用旧 token（不发新邮件）

### workspace context 切换

```
登录后 GET /api/me/workspaces → 返回 [{type: tenant, id, name}, {type: org, id, name, role}, ...]

前端默认选中"自家 tenant"，把 context 信息存 localStorage + 每次请求带 header：
X-Workspace-Context: tenant:{tenant_id}  或  org:{org_id}

后端中间件解析 header → 注入 OperationContext.workspace = {type, id}
所有跨 KB 操作的 RBAC 校验都基于此 context 走 fall-through 三步短路（见 ADR-0002）。

无 header 或 context 无效 → 400 Bad Request
```

### 鉴权机制

- **Session**：JWT（HS256），24h 有效期；payload 含 `{user_id, exp}`；放 `Authorization: Bearer <jwt>` header
- **Refresh token**：7d 有效期；用 `HttpOnly + Secure + SameSite=Strict` cookie；POST `/api/auth/refresh` 换新 JWT
- **MCP API Key**：见 [ADR-0004](./0004-http-mcp-server.md)，独立鉴权链路（绑定 user_id + workspace context）
- **密码哈希**：argon2id（推荐参数：`m=64MB, t=3, p=4`）
- **忘记密码**：POST `/api/auth/forgot-password { email }` → 发重置 link（一次性 token，1h 有效）→ POST `/api/auth/reset-password { token, new_password }`

## Considered Options

- **A. 纯邀请制（bootstrap owner + admin 邀请）**：rejected。运维需要预设 owner，门槛高；不适合"个人/小团队开放使用"场景。用户明确选自注册 + 邀请并存。
- **C. 纯管理员开通（无自注册无邀请）**：rejected。所有用户都靠 admin 手动开账户，运维负担重；扩展能力差；与"自部署内网 + 邀请制"的产品定位不符。
- **企业 SSO（SAML / OIDC）**：rejected for default。v4.2 自部署场景下自注册 + 邮箱密码已够；SSO 留作未来企业版升级路径（参 CONTEXT.md "自注册账户"条目的 _Avoid_）。
- **邮箱验证强制**：rejected for P1。增加注册流程摩擦；P1 不做，P2 加（未验证邮箱限制创建 organization 数量）。

## Consequences

- **schema 新增表**：
  - `tenants(id, owner_id, name, created_at)` — 每个 user 自注册时自动创建一条
  - `users(id, email UNIQUE, password_hash, is_email_verified, created_at, last_login_at)`
  - `organizations(id, owner_id, name, description, created_at)`
  - `org_members(org_id, user_id, role, joined_at, UNIQUE(org_id, user_id))`
  - `org_invites(token UUID PK, org_id, invited_email, role, invited_by, expires_at, accepted_at NULL, revoked_at NULL)`
  - `password_resets(token UUID PK, user_id, expires_at, used_at NULL)`
- **业务表加 `tenant_id` / `org_id` 列**：`knowledge_bases.tenant_id`（KB 创建在哪个 tenant 上下文）；`wiki_pages` / `content_chunks` / `sources` / `wiki_folders` 通过 `kb_id` 间接归属。
- **session 中间件**：FastAPI dependency 解析 JWT → 注入 `current_user`；workspace context 中间件解析 `X-Workspace-Context` header → 注入 `current_workspace`。
- **多设备登录**：不限制（同一 user 可多设备登录，每个设备独立 JWT）；refresh token 不撤销除非用户主动 logout all。
- **账户停用 / 删除**（Open Question A，留待后续）：
  - 软删除（`users.deleted_at`）：保留数据，禁止登录。
  - tenant 数据归属：停用 user 时，他的 tenant 下的 KB 默认保留（30 天 grace period），admin 可手动转移给其他 user 或彻底删除。
- **滥用防护**（Open Question B）：开放自注册有滥用风险（恶意注册几百个账户填满数据库）。候选防护：① 邮箱域名白名单（admin 配置允许的邮箱域名）；② 注册需 admin 审核批准；③ 默认开放 + 异常检测（同一 IP 注册超过 N 次触发告警）。v4.2 P1 默认开放，防护留作未来。
- **第一个用户**：docker-compose up 后第一个自注册的 user 与其他 user 完全等价——没有 super-admin 概念。**Open Question C**：是否需要一个 system admin 角色（能跨 tenant 看到所有数据 + 配置全局参数）？v4.2 P1 不做（运维直接连 DB 改配置）。

## Open Questions（留给未来 grilling）

- **Open Question A（账户停用 / 数据归属）**：用户停用 / 删除时，他自创的 KB / organization 怎么处理？候选：① 软删除 + 30 天 grace + admin 转移；② 强制 admin 在删除前手动指定接手人；③ 立即硬删除（不推荐）。
- **Open Question B（滥用防护）**：开放自注册的滥用风险如何应对？候选：① 默认开放 + 异常检测；② 邮箱域名白名单；③ 注册需 admin 审核。
- **Open Question C（system admin）**：是否需要跨 tenant 的 system admin 角色？v4.2 P1 默认不做（运维直接连 DB）。

## 参考实现

- FastAPI 鉴权：`fastapi-users` 库（支持 argon2id + JWT + 邮箱验证流程）或自实现
- 邀请 token：`uuid.uuid4()` 生成，存 `org_invites` 表
- workspace context 中间件：FastAPI Dependency，解析 `X-Workspace-Context` header
- 邮件发送：异步任务（Redis 队列），用 `aiosmtplib` 或 SMTP 服务商 SDK
