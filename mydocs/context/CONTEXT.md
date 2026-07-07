# 工作知识库（v4.2 设计中）

一款知识库管理 Web 服务，部署在用户内网服务器上，所有用户通过浏览器访问。内置 Agent Runtime，不依赖外部 CLI 工具。

## Language

### 部署与访问

**内网服务（Intranet Service）**:
单一部署在用户自有内网服务器上的 Web 服务进程；所有数据、计算、Agent 推理都在此进程内。
_Avoid_: 服务端、后端（这些词不区分单实例 vs 多实例，模糊）

**浏览器客户端**:
用户访问内网服务的唯一前端形态。零安装。
_Avoid_: 桌面客户端、Tauri 应用、胖客户端（v4.2 已放弃）

### 知识资产

**知识库（KB / Knowledge Base）**:
内容资产，单一 owner，可被共享到 0..N 个空间。owner 始终拥有完全控制权，不受任何空间权限约束。
_Avoid_: 数据库、文档库、笔记

**个人知识库（Personal KB）**:
owner 是当前用户、且未共享到任何空间的 KB。数据物理上仍在内网服务器的 Postgres 里，无独立"本地存储"概念。
_Avoid_: 本地知识库、私有数据库、离线库

**组织（Organization）**:
跨 tenant 的共享容器。由创建者（org admin）邀请成员加入，通过 `kb_shares` 挂载来自不同 tenant 的 KB。日常语境下也叫"共享空间"，但术语层面用 Organization 以与 Tenant 区分。
_Avoid_: 团队、项目、群组、workspace（v4.2 已弃用——原 workspace 概念模糊了 tenant 与 org 的边界）

**KB 共享（KBShare）**:
KB 与组织之间的显式共享关系，三元组 `(kb_id, org_id, permission)`。**无 user_id 字段**——共享针对组织而非个人。org 成员变动时只改 `org_members` 一张表，KB 共享记录自动沿用。
_Avoid_: kb_grants.user_id（粒度错误）、ACL 单独建表（无组织语义）、按用户授权（人员变动运维噩梦）

**OKF（Open Knowledge Format）** [v4.2 已弃用]:
早期设计的"知识库可移植捆绑格式（zip）"，原计划用于"导出带走 + 导入回来"。v4.2 grilling 确认弃用——自部署内网服务场景下实例迁移用 `pg_dump` 已够，跨 wiki 系统迁移用 MD 导出包 + frontmatter 已够。再设计一个独立格式属于过度工程。
_Avoid_:（条目已弃用，新增产品不要使用此概念）

**MD 导出包（Markdown Export Bundle）**:
v4.2 唯一的导出格式。zip 包含：① markdown 文件（按 `wiki_path` 目录结构组织）；② 每个文件头部 YAML frontmatter（`page_type` / `slug` / `chunk_refs` / `folder_path` / `version`）。**不导出 embeddings**——导入时按 KB 当前绑定模型重嵌入。适合"人读 + 跨 wiki 系统迁移（Obsidian / Logseq / 其他）"。RAG 类型 KB 不支持整库导出（无 wiki 页面），只支持原始文档下载。
_Avoid_: OKF（已弃用）、包含 embedding 的便携包（v4.2 不做，需要时用 pg_dump）、跨实例同步通道（导出是一次性快照，不是同步）

### 数据模型与存储

**KB 级嵌入模型绑定（KB-level Embedding Model Binding）**:
KB 创建时绑定一个嵌入模型 + 维度，库内所有 chunks 维度一致；不同 KB 可以用不同模型。模型升级 = 新建 KB 或全量重嵌入，不做混合维度比较。
_Avoid_: 全局统一模型、跨 KB 向量比较、维度 padding（反模式）

**多维度共存（Multi-dimension Coexistence）**:
content_chunks 表用 halfvec 不带 N 的列声明 + embedding_dim 字段，同表共存不同维度的向量；每个维度单独建 partial HNSW 索引。具体 SQL 与 cast 细节见 [ADR-0001](./docs/adr/0001-halfvec-multi-dim.md)。
_Avoid_: 维度 padding 到固定 halfvec(N)、按 KB 分表、强制全局单模型

### 页面与图谱模型

**页面类型（PageType）**:
wiki 页面的 7 种枚举。自动生成 5 种：`summary`（文档摘要）/ `entity`（实体页）/ `concept`（概念页）/ `index`（系统索引页，slug 固定）/ `log`（系统日志页，slug 固定）；Agent 手建 2 种：`synthesis`（综合分析）/ `comparison`（对比页）。`index`/`log` 是系统页，排除在用户目录之外。
_Avoid_: 文档类型（doc_type 是 chunks 表的字段，指原始文档格式如 pdf/md/html，与 PageType 是两回事）、页面分类

**链接图边（Link Graph Edges）**:
页面之间的"图谱"关系，无类型、无权、有向。从 markdown `[[xxx]]` wikilink 正则抽取，双向冗余存 `pages.in_links` / `pages.out_links` 数组。图谱可视化只能展示"谁连谁"，不能展示"什么关系"——这是有意的简化（详见 [ADR-0003](./docs/adr/0003-three-edge-model.md)）。
_Avoid_: 类型化边、语义边、link_type 字段（永久放弃——LLM 抽取不可靠，70%+ 兜底到 related_to）

**目录树边（Folder Tree Edges）**:
页面的归档结构。两套并存：`folder_id`（source of truth，引用 `wiki_folders.id`）+ `parent_slug`（语义父级，可选）。深度硬上限 3 层。
_Avoid_: 单一 parent_id 邻接表（无法兼顾"按文件夹归类"和"语义父子"两种需求）

**物化路径缓存（Materialized Path Cache）**:
`category_path` / `depth` / `wiki_path` 三个字段，全是从 `folder_id` 链路反向重算的缓存。每次写 page 都重算（应用层 service 透明兜底）。避免列表/索引/搜索查询时 JOIN `wiki_folders` 表。
_Avoid_: 实时 JOIN 算路径（性能差）、不缓存（每次查询都递归 CTE）

**溯源边（Provenance Edges）**:
页面 → 原文档/chunk 的引用。`source_refs`（文档级，格式 `<kb_id>|<doc_title>`）+ `chunk_refs`（chunk 级 UUID）。`summary` 页通常 `chunk_refs` 为空；`entity`/`concept`/`synthesis`/`comparison` 页带 chunk 级引用。用途：原文档删除时清掉对应引用、对话里点"查看证据"跳回原文。
_Avoid_: 单一 doc_id 外键（无法表达"这一段综合了 3 篇文档的 5 个 chunk"）、不带 chunk 级精度（无法精确溯源）

**Slug 唯一性（KB-Scoped Slug Uniqueness）**:
slug 在同一个 KB 内唯一（`UNIQUE(kb_id, slug)`），**跨 KB 不唯一**。两个 KB 都有"苹果"实体不冲突。`index` / `log` 两个 slug 在每个 KB 内保留给系统页，用户不能占用。
_Avoid_: 全局 slug 唯一（跨 KB 撞名是常态，强制全局唯一会让"苹果"被某个 KB 独占）

### AI 子系统

**Agent Runtime**:
内置的 AI 子系统。核心是一个 OpenAI 协议兼容的 LLM Client（一家抽象，覆盖 OpenAI / Azure / DeepSeek / Qwen / GLM / Kimi），加 Anthropic / Google 独立适配器。用户在 Web UI 内直接对话，由系统自带工具集（搜索、图谱遍历、文档检索）支撑。
_Avoid_: stdio MCP（作为 client 接入外部 CLI）、stdio 子进程、CLI agent（v4.2 已放弃这条路线）
_保留_: HTTP MCP server（作为 server 暴露 8 个工具给外部 AI 应用，详见 [ADR-0004](./docs/adr/0004-http-mcp-server.md)）

**HTTP MCP 工具集（Streamable HTTP MCP Server）**:
FastAPI 服务在 `/mcp` 端点暴露的 MCP server，使用 Streamable HTTP 协议（spec 2025-03-26+）。8 个工具：`list_kbs` / `use_kb` / `list_pages` / `search` / `read` / `related` / `chat` / `update`。外部 AI 应用（Claude Desktop 通过 mcp-remote 桥接、Cursor、其他 Web 应用）通过 HTTP 接入。
_Avoid_: stdio MCP server（需要本地子进程，与 v4.2 全面 Web 化冲突）

**API Key 鉴权（MCP）**:
MCP 客户端访问 `/mcp` 端点的鉴权方式。用户在 Web UI 生成 API Key（绑定 user_id + workspace context），客户端在 `Authorization: Bearer <key>` 里带 key。RBAC 走 [ADR-0002](./docs/adr/0002-tenant-org-rbac.md) 的 fall-through 三步短路，context 由 API Key 绑定时确定。
_Avoid_: OAuth 2.1（MCP spec 推荐但 v4.2 不做，留作企业版升级路径）、无鉴权（不安全）

**LLM Provider Registry**:
厂商元数据表。每条记录：display_name、base_url、protocol（openai / anthropic / gemini）、默认模型列表。运行时根据 provider 选择对应的 client 实现。

**BYOK（Bring Your Own Key）**:
LLM API Key 的所有权模型。每个用户在个人设置里填自己的 key，加密存储。共享 KB 查询时由查询者的 key 计费——产品不介入 token 采购/分配/报销，只提供「接入大模型」的能力层。key 来源（公司发 / 自费）是用户与公司之间的私事。
_Avoid_: 团队 key、空间 key、全局 key、统一采购

**统一产品形态**:
v4.2 是一个产品，从「单人自用」到「小团队」到「公司多团队」无缝扩展。区别不在产品形态，而在**部署时启用的模块**：单人 = 自建账户；团队 = 邀请制 + RBAC；公司 = 强制 SSO + RLS。

### 技术栈

**Next.js Web**:
浏览器客户端的实现。仅做前端 + BFF（轻量聚合/鉴权转发），不承担业务逻辑。
_Avoid_: API Routes 业务化（v4.2 反对）

**FastAPI 服务**:
Python 后端。承担业务逻辑、Agent Runtime、文档解析、向量检索、RBAC 校验、异步任务。
_Avoid_: Node 后端（v4.2 已放弃）、Next.js API Routes 业务化

**Redis + 任务队列**:
异步任务（PDF 解析、嵌入生成、图构建、向量索引）的执行通道。Python worker 进程消费。
_Avoid_: 桌面端 setInterval（v4.2 已不可行）

### 隔离与认证

**自注册账户（Self-Signup Account）**:
任何人访问产品注册账户（邮箱+密码）。账户不依赖公司 SSO，产品自带完整账户体系。
_Avoid_: 公司 SSO、LDAP、SAML、OIDC（v4.2 不做，除非未来有具体企业客户需求）

**邀请制加入空间**:
共享空间的 admin 生成邀请链接（带 token），受邀者打开链接即加入空间为成员（默认 viewer 角色，admin 可改）。无邀请则不能加入。
_Avoid_: admin 集中开账户、IT 运维介入

### 权限模型

**租户（Tenant）**:
"自家空间"概念。每个用户默认拥有一个自家 tenant，自创 KB 都挂在 caller 当前 tenant 上下文下。tenant 内的角色（TenantRole: owner / admin / contributor / viewer）是用户在自家组织的身份。
_Avoid_: "我的工作区"（容易与 Organization 混淆）、个人空间、私有域

**TenantRole**:
tenant 内的角色层级：`owner`（创建者）/ `admin` / `contributor` / `viewer`。`viewer` 触发 `applyTenantRoleCap` 硬封顶。

**OrgMemberRole**:
organization 内的角色层级：`admin` / `editor` / `viewer`。`admin` 是 org 创建者或被授予权的成员；`editor` 可写共享 KB；`viewer` 只读。

**自有即全权（Owner-Bypass）**:
合并算法第 1 步短路：当 `caller.tenantID == kb.tenantID` 时，无论 caller 在自家 tenant 是 viewer 还是 owner，对自家 KB 都返回 Admin。这是有意的设计——避免重蹈 PRD v4.2 三档 min() 让 KB 所有者被自家 viewer 角色压制的逻辑 bug。
_Avoid_: "所有者也是 viewer 时取 min"（反模式）

**Fall-Through 三步短路合并（Fall-Through Resolution）**:
跨 KB 操作的权限解析算法。依次短路：① 自有 KB → Admin；② 共享 KB → `effective = min(share_perm, my_org_role)`，再过 `applyTenantRoleCap` 硬封顶；③ 通过 agent 间接可见 → Viewer；④ 否则 403。具体伪代码与决策见 [ADR-0002](./docs/adr/0002-tenant-org-rbac.md)。
_Avoid_: 三档 min()（已弃用，会让 owner 被自家角色压制）、单档 workspace 默认权限（粒度不够）

**ApplyTenantRoleCap**:
硬封顶规则，且**只封一种情况**：`my_tenant_role == Viewer && effective >= Editor` → 砍到 Viewer。其他情况一律原样返回。这是有意的最小化封顶，避免重蹈 PRD 三档 min() 的覆辙。
_Avoid_: 全档 min()（过度保守）、无封顶（tenant 级 viewer 可能越权写共享 KB）

**强制工作空间隔离（Mandatory Workspace Isolation）**:
任何用户查询都必须落在一个具体 workspace 上下文中（自家 tenant 或某 organization）；不存在「跨 workspace 自由搜索」。每次跨 KB 操作先调 `resolveKBAccessOnce(caller, kb)` 校验。应用层 RBAC。
_注_: v4.2 暂不做 Postgres RLS——RLS 是企业级兜底，自注册+邀请制场景下应用层 RBAC 已够。RLS 留作未来企业版升级路径。

## v4.1 → v4.2 已弃用术语

| v4.1 术语 | v4.2 状态 | 原因 |
|---|---|---|
| 桌面客户端（Tauri） | 弃用 | 全面 Web 化 |
| 本地 PGLite 引擎 | 弃用 | 数据集中存内网服务器 |
| Rust sidecar（PDF 解析） | 弃用 | PDF 解析回服务端 Python worker + Redis 队列（pdfium/pdfplumber/unstructured） |
| stdio MCP server | 弃用 | 不再接入外部 CLI；保留的是 HTTP MCP server（见 [ADR-0004](./docs/adr/0004-http-mcp-server.md)） |
| 个人模式 / 团队模式（双模式） | 弃用 | 只有"Web 模式"一种 |
| OKF（Open Knowledge Format） | 弃用 | MD 导出包 + frontmatter 已够；实例迁移用 pg_dump |
| 三档 RBAC（workspace/kb_grant/membership min()） | 弃用 | 改为 tenant + organization 两层 + kb_shares + fall-through 合并（见 [ADR-0002](./docs/adr/0002-tenant-org-rbac.md)） |
| 8 种语义边 / 类型化 link_type | 弃用 | 改为无类型有向 wikilink 边 + 三套边并存（见 [ADR-0003](./docs/adr/0003-three-edge-model.md)） |
| halfvec(3072) + 维度 padding | 弃用 | 改为 halfvec 不带 N + embedding_dim 字段 + partial HNSW（见 [ADR-0001](./docs/adr/0001-halfvec-multi-dim.md)） |
