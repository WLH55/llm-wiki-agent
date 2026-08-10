# 工作知识库（v4.2 设计中）

一款知识库管理 Web 服务，部署在用户内网服务器上，所有用户通过浏览器访问。内置 Agent Runtime，不依赖外部 CLI 工具。

> **MVP 范围提示**：本术语表描述**长期架构方向**——不是所有条目都在 MVP 阶段实现。MVP（P1）只实现双路径核心闭环（KB 创建 + 文档上传 + 检索 + chat + Wiki 抽取 + 手动编辑）+ 极简鉴权（bootstrap owner + 系统兜底 key）。具体砍点与 schema 预留策略见 [ADR-0008](./docs/adr/0008-mvp-scope.md)。

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
RAG 与 Wiki 共享的数据归属、生命周期和文档分块策略边界。KB 不携带 RAG/Wiki 类型、嵌入模型或能力开关；具体能力由独立配置定义。
_Avoid_: 数据库、文档库、笔记、RAG 类型 KB、Wiki 类型 KB

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
v4.2 唯一的导出格式。zip 包含按页面目录组织的 Markdown，以及 `page_type`、`slug`、`folder_path`、`version`、文档来源和原文证据等 frontmatter；不导出 embeddings。适合人读和跨 Wiki 系统迁移；没有 Wiki 页面的 KB 只提供原始文档下载。
_Avoid_: OKF（已弃用）、包含 embedding 的便携包（v4.2 不做，需要时用 pg_dump）、跨实例同步通道（导出是一次性快照，不是同步）

### 数据模型与存储

**RAG 配置（RAG Configuration）**:
KB 可选的 RAG 能力配置，只保存向量/关键词检索开关与嵌入模型。分块是 RAG/Wiki 共享摄取策略，不属于 RAG 配置。
_Avoid_: 在 RAG 配置中定义第二套分块规则、用知识库类型隐含 RAG 配置

**Wiki 配置（Wiki Configuration）**:
KB 可选的 Wiki 能力配置，独立保存启用状态、页面生成模式、生成模型与生成策略。Wiki 配置不依赖 RAG 配置；暂停配置不会删除已有页面。
_Avoid_: 用 RAG 开关隐含 Wiki 能力、把 Wiki 生成模型与 embedding 模型混为一谈

**KB 级嵌入模型绑定（KB-level Embedding Model Binding）**:
RAG 配置绑定一个嵌入模型 + 维度，库内所有有效 chunks 维度一致；不同 KB 可以用不同模型。模型升级需要全量重嵌入，不做混合维度比较。
_Avoid_: 全局统一模型、跨 KB 向量比较、维度 padding（反模式）

**多维度共存（Multi-dimension Coexistence）**:
content_chunks 表用 halfvec 不带 N 的列声明 + embedding_dim 字段，同表共存不同维度的向量；每个维度单独建 partial HNSW 索引。具体 SQL 与 cast 细节见 [ADR-0001](./docs/adr/0001-halfvec-multi-dim.md)。
_Avoid_: 维度 padding 到固定 halfvec(N)、按 KB 分表、强制全局单模型

**数据源（Source）**:
KB 内的文档来源或连接器；一个 Source 可以产生多篇 Document。Source 保存类型、非敏感配置、增量游标、启停状态和最近成功同步时间；每种类型由一个 `SourceAdapter` 实现，运行状态与错误属于 Processing Run。所有 Source 平等，不参与检索加权或更新覆盖优先级。
_Avoid_: 每 source 单独建表（schema 膨胀）、source boost_factor（YAGNI）、source 级 RBAC（粒度过细）

**逻辑文档（Document）**:
KB 中一篇来源文档的稳定身份；同一来源文档后续上传或同步时仍是同一个 Document，并在其下产生新的 Document Revision。
_Avoid_: 把一次上传、一次同步或一个具体文件称为 Document

**文档版本（Document Revision）**:
Document 在某次上传或同步时取得的不可变内容快照；原文件、内容指纹和来源版本属于 Revision，`status` 表示它当前能否成为生效版本。每次处理尝试的错误和执行时间属于 Processing Run；处理失败的 Revision 不取代既有生效版本。
_Avoid_: 用覆盖 Document 的方式保存更新、把解析重试称为新版本、在 Revision 和 Processing Run 中重复保存运行诊断

**候选版本（Candidate Revision）**:
已经完成共享解析与分块、`status=ready`，但尚未通过当前 KB 激活门槛的 Document Revision。启用向量检索时，候选版本必须完成整套 chunks 的 embedding 后才能成为 Active Revision。
_Avoid_: 把 `ready` 直接等同于 Active、让未完成向量化的新版本替换仍可服务的旧版本

**生效版本（Active Revision）**:
Document 当前已经通过激活门槛、正式供 RAG/Wiki 消费的 Revision。未启用向量检索时共享解析与分块完成即可激活；启用时还必须完成候选 chunks 的 embedding。Wiki 生成不是激活门槛。
_Avoid_: 最新上传版本（最新收到的版本可能仍在处理或已经失败）

**生效分块集（Active Chunk Set）**:
Document 的 Active Revision 当前共享的一组 `content_chunks`，同时作为 RAG 召回单元和 Wiki Map 输入。它可从 Revision 重建；两阶段激活期间允许候选 chunks 与旧 Active Chunk Set 共存，但在线读取只消费 Active。详见 [ADR-0013](./docs/adr/0013-shared-content-chunk-substrate.md)。
_Avoid_: 把候选 chunks 暴露给在线检索、RAG chunks（会误以为 Wiki 不能消费）、历史 chunk 版本库、把可重建 chunks 当成不可变业务事实

**处理运行（Processing Run）**:
一次可独立调度或取消的业务处理尝试；保存目标、配置快照、整体状态、错误和起止时间。RQ 自动重试是同一 Run 的再次执行，只有终态后的业务重跑才创建新 Run。父 Run 只对独立子任务进行编排归组，不代表内部执行步骤，也不要求兄弟 Run 串行。Run 不保存含义模糊的“主要模型”。
_Avoid_: 把队列自动重投称为新 Run、把普通函数步骤建成 Run、用父 Run 状态覆盖子 Run 的独立成败、在 Revision 中复制运行诊断

**处理阶段（Processing Span）**:
Processing Run 内一次计划或实际执行的可观测阶段；保存阶段状态、具体模型、token、指标、错误和起止时间。`skipped` 表示主动不执行，`cancelled` 表示因用户、Run 或上游失败而中止。Span 可以串行或并行；固定阶段顺序和依赖来自应用注册表与编排代码，`parent_span_id` 只表达嵌套归属。
_Avoid_: 用 `skipped` 掩盖上游失败、把 Span 当成可独立排队的任务、在数据库保存全局执行序号、在 Run 中重复保存阶段模型

**BM25 关键词检索（BM25 Keyword Retrieval）**:
`knowledge_search` 的词法召回路径，由 PostgreSQL `pg_search` 扩展对 `content_chunks.text` 建立真正 BM25 索引，并与向量召回通过 RRF 融合。
_Avoid_: 把 PostgreSQL `tsvector` + `ts_rank` / `ts_rank_cd` 全文排序称为 BM25

**IndexingStrategy（旧 KB 级检索能力开关）** [已弃用]:
旧设计把 `vector_enabled` / `keyword_enabled` / `wiki_enabled` / `graph_enabled` 直接放在 `knowledge_bases`。2026-07-27 数据表评审决定 KB 保持为轻量共享根，由独立的 RAG 配置和 Wiki 配置表达能力。
_Avoid_: 继续向 `knowledge_bases` 增加能力开关、用单一 `type` 把 KB 固化为 RAG 或 Wiki

**chunk_type（旧 content_chunks 来源区分）** [已弃用]:
旧设计用 `document` / `wiki_page` / `image_ocr` / `image_caption` 区分同表内容；最终 `content_chunks` 只保存 Document Revision 派生的共享原文块，不保存 Wiki 页面，因此不需要 `chunk_type` 或 `wiki_page_id`。
_Avoid_: 把 Wiki 页面或其他派生内容静默写入 RAG chunk 池

### 页面与图谱模型

**页面类型（PageType）**:
wiki 页面的 7 种枚举。自动生成 5 种：`summary`（文档摘要）/ `entity`（实体页）/ `concept`（概念页）/ `index`（系统索引页，slug 固定）/ `log`（系统日志页，slug 固定）；Agent 手建 2 种：`synthesis`（综合分析）/ `comparison`（对比页）。`index`/`log` 是系统页，排除在用户目录之外。
_Avoid_: 文档类型（doc_type 是 chunks 表的字段，指原始文档格式如 pdf/md/html，与 PageType 是两回事）、页面分类

**页面预览（Page Excerpt）**:
对任意 Wiki 页面的简短概括，用于目录列表、搜索结果和 Agent 在读取全文前筛选页面。它不是一种页面类型；文档摘要页仍称为 `summary` 页面，其完整内容属于页面正文。
_Avoid_: 把页面预览称为 summary 字段、把预览文本当作完整页面正文

**链接图边（Link Graph Edges）**:
页面之间由正文 wikilink 形成的无类型、无权、有向关系。链接关系独立于页面正文保存，可用于反向链接、邻居遍历和图谱可视化；它只表达"谁链接谁"，不表达预定义语义类型。
_Avoid_: 把链接数组塞进页面本体、类型化边、语义边、link_type

**目录树边（Folder Tree Edges）**:
页面的归档结构，只表达页面位于哪个目录以及目录之间的父子关系；它不表达页面主题之间的语义关系。
_Avoid_: 把页面语义关系混入目录树、为页面同时维护目录父级和语义父级

**页面目录归属（Page Folder Membership）**:
普通 Wiki 页面可以归属于一个目录，也可以位于 Wiki 根目录；`folder_id` 是页面导航位置的唯一事实来源。页面移动表示改变目录归属，页面自身不保存另一套路径。
_Avoid_: 页面物化路径缓存、在页面与目录上重复维护同一条路径

**溯源边（Provenance Edges）**:
Wiki 页面到具体 Document Revision 及其原文证据的关系：文档引用锁定版本，证据引用保存准确引文与位置，并可通过可空 `content_chunk_id` 回到生成时的共享 chunk。
_Avoid_: 把溯源数组塞进页面本体、只引用可删除的 chunk ID、让 AI 自由改写证据原文

**Slug 唯一性（KB-Scoped Slug Uniqueness）**:
slug 是页面创建后不可修改的稳定链接标识，在同一个 KB 内唯一，跨 KB 可以重复。页面改名只修改标题和别名；`index` / `log` 两个 slug 在每个 KB 内保留给系统页。
_Avoid_: 全局 slug 唯一、用修改 slug 实现页面改名、批量重写其他页面的 wikilink

**页面别名（Page Alias）**:
Wiki 页面名称的其他常用写法，用于让用户通过简称、旧称或中英文名称找到同一页面。别名不改变页面身份，也不作为页面链接的解析目标。
_Avoid_: 用别名代替 slug、依赖别名唯一、用有歧义的别名解析页面链接

### AI 子系统

**Agent Runtime**:
内置的 AI 子系统。核心是一个 OpenAI 协议兼容的 LLM Client（一家抽象，覆盖 OpenAI / Azure / DeepSeek / Qwen / GLM / Kimi），加 Anthropic / Google 独立适配器。**双 AI 通道**（详见 [ADR-0006](./docs/adr/0006-agent-runtime-byok.md)）：① 内置 Agent（Web UI 对话）+ ② 外部 MCP（HTTP MCP /chat 工具调用）；两条通路最终都走同一个 LLMClient 抽象 + BYOK。
_Avoid_: stdio MCP（作为 client 接入外部 CLI）、stdio 子进程、CLI agent（v4.2 已放弃这条路线）

**Agent Runtime 内部工具集（Agent Internal Tools）**:
内置 Agent 的 LLM 可调用的 5 个系统工具（Python 函数直接调用，不走 HTTP）：`search_kb` / `traverse_graph` / `read_page` / `read_chunks` / `write_wiki_page`。**不能调用 MCP 工具**（避免循环：MCP chat → 内置 Agent → MCP 工具）。与 MCP 8 个工具的差异：内部工具是给内置 Agent 用的，MCP 工具是给外部 AI 应用用的。详见 [ADR-0006](./docs/adr/0006-agent-runtime-byok.md)。
_Avoid_: 内置工具走 HTTP（性能差）、内置工具与 MCP 工具合并（语义混淆 + 循环风险）

**HTTP MCP 工具集（Streamable HTTP MCP Server）**:
FastAPI 服务在 `/mcp` 端点暴露的 MCP server，使用 Streamable HTTP 协议（spec 2025-03-26+）。8 个工具：`list_kbs` / `use_kb` / `list_pages` / `search` / `read` / `related` / `chat` / `update`。外部 AI 应用（Claude Desktop 通过 mcp-remote 桥接、Cursor、其他 Web 应用）通过 HTTP 接入。
_Avoid_: stdio MCP server（需要本地子进程，与 v4.2 全面 Web 化冲突）

**API Key 鉴权（MCP）**:
MCP 客户端访问 `/mcp` 端点的鉴权方式。用户在 Web UI 生成 API Key（绑定 user_id + workspace context），客户端在 `Authorization: Bearer <key>` 里带 key。RBAC 走 [ADR-0002](./docs/adr/0002-tenant-org-rbac.md) 的 fall-through 三步短路，context 由 API Key 绑定时确定。
_Avoid_: OAuth 2.1（MCP spec 推荐但 v4.2 不做，留作企业版升级路径）、无鉴权（不安全）

**LLM Provider Registry**:
厂商元数据表（admin 维护）。每条记录：`display_name` / `base_url` / `protocol`（openai / anthropic / gemini）/ `default_models` / `is_active`。默认预置 8 个 provider（OpenAI / Azure / DeepSeek / Qwen / GLM / Kimi / Anthropic / Google）；admin 可添加自部署模型（vLLM / Ollama，填 `base_url=http://...:8000/v1` + `protocol=openai`）。详见 [ADR-0006](./docs/adr/0006-agent-runtime-byok.md)。
_Avoid_: 用户自定义 provider（admin 维护，避免脏数据）、硬编码 provider 列表（不可扩展）

**BYOK（Bring Your Own Key）**:
LLM API Key 的所有权模型。每个用户在个人设置里填自己的 key（Fernet 对称加密，密钥派生自 env var `LLM_KEY_ENCRYPTION_KEY`），可填多个 provider 的 key。共享 KB 查询时由查询者的 key 计费——产品不介入 token 采购/分配/报销，只提供「接入大模型」的能力层。详见 [ADR-0006](../adr/0006-agent-runtime-byok.md)。
**嵌入模型 vs LLM 模型分离**：KB 创建时绑定嵌入模型（导入者 key 计费）；用户对话/抽取时用 LLM 模型（查询者 key 计费）；query embedding 用查询者 key。
**没 key 兜底**：用户没填任何 BYOK key → 向量检索降级为 BM25 关键词检索；chat / 抽取 / 综述功能禁用。
_Avoid_: 团队 key、空间 key、全局 key、统一采购、系统兜底 key（v4.2 不做，留作企业版升级路径）

**意图分类（Intent Classification，零 LLM）** [v4.2 已弃用]:
原方案是对话入口的关键词/规则路由（5 类：`chat` / `search_only` / `summarize` / `compare` / `extract_entities`）。v4.2 grilling 确认弃用——改为 IndexingStrategy KB 级配置 + Agent 显式选检索工具。详见 [ADR-0010](../adr/0010-mvp-wiki-rag-separation.md)。
_Avoid_:（条目已弃用，新增产品不要使用此概念）

**双路径检索（Dual-Path Retrieval）**:
两条独立检索路径，**MVP 不写入、不混合召回、不做联合排序**。路径 A `wiki_search`：在 `wiki_pages` 的标题、slug、别名、预览和正文中检索并按字段重要性排序，不走向量/BM25。路径 B `knowledge_search`：原始 `content_chunks` + 向量（pgvector）+ BM25 + RRF 融合，不包含 Wiki 页面。详见 [ADR-0010](../adr/0010-mvp-wiki-rag-separation.md)。
_Avoid_: 双路径间 RRF 联合（rejected，跨路径排序语义模糊）、query 级别用户手动选模式（被 IndexingStrategy 替代）

**wiki_search（POSIX 正则 + 字段权重）**:
路径 A 的检索方式。独立端点 `GET /api/v1/kb/{id}/wiki/search?q=...&limit=10`，检索 `wiki_pages` 表。完全不用向量/embedding/BM25，用 PG 内建 `~*`（POSIX 正则，大小写不敏感）+ 字段权重 CASE 排序。支持正则特性（`|` 交替 / `.*` 串联 / `^` 前缀）。中文是字节级子串匹配（不需要 zhparser）。limit 默认 10，硬上限 50。
_Avoid_: BM25 over wiki_pages（相似度排序会把"仅提及关键词"的页面排到"标题就是关键词"的页面之前）、tsvector + ts_query 全文检索（不支持任意正则 + 中文需 zhparser 分词扩展）

**wiki chunk boost** [MVP 不启用]:
MVP 不生成 Wiki chunk，也不在 `content_chunks` 保留 `chunk_type` / `wiki_page_id`，不启用固定 1.3 加权。`wiki_page_evidence_refs.content_chunk_id` 只连接 Wiki 证据与共享原文块，不代表 Wiki 页面已进入 RAG 召回池；融合启用前仍必须完成独立评测、血缘去重和一手证据优先设计，并另立 ADR。
_Avoid_: 把可空关联描述成已实现融合、在没有同源去重时让 Wiki 转述挤占原文 top-k

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
异步任务（PDF 解析、嵌入生成、Wiki 生成、向量索引）的投递通道。API 是生产者，独立 Python Worker 是消费者；二者可以复用同一个镜像和 Python 包，但由不同入口进程执行。代码位于 `app/parsers` 不代表由 API 进程执行，正式解析由 Worker 导入共享 Parser 实现。Redis 还允许保存可丢失的同 KB Wiki 租约锁和删除墓碑；任务权威状态、进度、Map/Reduce 结果和最终业务数据均不放在 Redis。详见 [ADR-0017](../adr/0017-redis-ephemeral-wiki-coordination.md)。

当前实现使用 RQ：业务上是异步投递，但标准 RQ Worker 一次只执行一个 Job；`asyncio.run` 只让单个 Job 能调用协程，不提供多 Job 协程并发。目标 Worker 运行时仍在评估，尚未批准保留 RQ 或切换到 `arq` 等 async-native 队列，也未批准具体并发数和队列容量。
_Avoid_: 桌面端 setInterval（v4.2 已不可行）、把 Redis checkpoint 当成任务进度事实、无 owner token 的租约锁、把消息异步等同于协程并发、因代码目录位置误判实际执行进程

### 隔离与认证

**自注册账户（Self-Signup Account）**:
任何人访问产品 URL 注册账户（邮箱+密码）。注册成功后**自动创建一个自家 tenant**（owner=自己，独占，不可邀请人）。账户不依赖公司 SSO，产品自带完整账户体系。详见 [ADR-0005](../adr/0005-self-signup-and-invitation.md)。
_Avoid_: 公司 SSO、LDAP、SAML、OIDC（v4.2 不做，除非未来有具体企业客户需求）

**邀请制加入空间（Invitation-Based Org Membership）**:
organization 的 owner/admin 生成邀请链接（带 `invite_token` UUID），受邀者打开链接 → 已登录则直接加入该 org（默认 viewer 角色，admin 可改），未登录则先跳注册再加入。**邀请 token 7 天有效、一次性使用、可主动撤回**。无邀请则不能加入。详见 [ADR-0005](../adr/0005-self-signup-and-invitation.md)。
_Avoid_: admin 集中开账户、IT 运维介入、永久有效的邀请 link（安全风险）

**Workspace Context 切换**:
用户登录后必须选择当前 workspace context（自家 tenant / 某 organization），前端把 context 信息存 localStorage，每次 API 请求带 `X-Workspace-Context: tenant:{id}` 或 `org:{id}` header。无 context 的查询一律 400。一个 user 可同时属于 1 个自家 tenant + N 个 organization，随时切换。
_Avoid_: 隐式默认 context（用户不知道自己在哪个空间会出大问题）、跨 workspace 自由搜索（违反强制工作空间隔离）

**JWT Session + Refresh Token**:
v4.2 的鉴权机制。JWT（HS256，24h 有效期）放 `Authorization: Bearer <jwt>` header；refresh token（7d 有效期）放 `HttpOnly + Secure + SameSite=Strict` cookie。MCP API Key（[ADR-0004](../adr/0004-http-mcp-server.md)）是独立鉴权链路，不复用 JWT。密码哈希用 argon2id。
_Avoid_: 跨域 cookie（CORS 麻烦）、Session 表（无状态 JWT 已够）、明文密码（绝对禁止）

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
跨 KB 操作的权限解析算法。依次短路：① 自有 KB → Admin；② 共享 KB → `effective = min(share_perm, my_org_role)`，再过 `applyTenantRoleCap` 硬封顶；③ 通过 agent 间接可见 → Viewer；④ 否则 403。具体伪代码与决策见 [ADR-0002](../adr/0002-tenant-org-rbac.md)。
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
| stdio MCP server | 弃用 | 不再接入外部 CLI；保留的是 HTTP MCP server（见 [ADR-0004](../adr/0004-http-mcp-server.md)） |
| 个人模式 / 团队模式（双模式） | 弃用 | 只有"Web 模式"一种 |
| OKF（Open Knowledge Format） | 弃用 | MD 导出包 + frontmatter 已够；实例迁移用 pg_dump |
| 三档 RBAC（workspace/kb_grant/membership min()） | 弃用 | 改为 tenant + organization 两层 + kb_shares + fall-through 合并（见 [ADR-0002](../adr/0002-tenant-org-rbac.md)） |
| 8 种语义边 / 类型化 link_type | 弃用 | 改为无类型有向 wikilink 边 + 三套边并存（见 [ADR-0003](../adr/0003-three-edge-model.md)） |
| halfvec(3072) + 维度 padding | 弃用 | 改为 halfvec 不带 N + embedding_dim 字段 + partial HNSW（见 [ADR-0001](../adr/0001-halfvec-multi-dim.md)） |
| 意图分类（Intent Classification） | 弃用 | IndexingStrategy KB 级配置 + Agent 显式选工具替代（见 [ADR-0010](../adr/0010-mvp-wiki-rag-separation.md)） |
| query 级别用户手动选模式（RAG/Wiki 切换） | 弃用 | KB 创建时配置 IndexingStrategy 决定能力（见 [ADR-0010](../adr/0010-mvp-wiki-rag-separation.md)） |
| Wiki 页面在 MVP 写入 RAG 并固定 boost 1.3 | 弃用 | Wiki/RAG 先独立运行，字段与血缘全预留；通过独立评测和去重设计后再决定是否融合（见 [ADR-0010](../adr/0010-mvp-wiki-rag-separation.md)） |
