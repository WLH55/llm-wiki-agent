# CONTEXT.md — 领域术语表

> 本项目数据库层于 2026-08-20 决定全量采用 WeKnora 领域模型（见 `docs/adr/0001-adopt-weknora-schema.md`）。
> 以下术语以 WeKnora 的统一语言（ubiquitous language）为准；旧模型的叫法在「曾用名」列，仅用于对照历史代码与文档。

## 租户与身份

| 术语 | 定义 | 曾用名 |
|---|---|---|
| **Tenant（租户）** | 资源与计费的隔离边界，持有模型、检索、存储等全局配置与配额 | tenant（含义不变） |
| **User（用户）** | 可登录的账户，可属于多个租户，可有平台级管理员身份 | user（含义不变） |
| **TenantMember** | 用户在租户内的成员关系与角色（owner/admin/contributor/viewer） | —（旧模型无此概念，角色内联在 user 上） |
| **Invitation（租户邀请）** | 拉用户进租户的凭证，支持定向邀请与分享链接两种形态 | — |
| **ApiKey（租户/平台密钥）** | 程序化访问凭证，哈希存储，可限定知识库白名单与能力清单 | — |
| **AuditLog（审计日志）** | 谁、何时、对什么目标、做了什么操作、成功与否 | —（旧模型仅有检索日志） |

## 模型配置

| 术语 | 定义 | 曾用名 |
|---|---|---|
| **Model（模型配置）** | 一个已注册的 LLM/Embedding/Rerank 等模型的接入配置，按用途分型 | models 表（含义近似，新增多类型） |

## 知识库核心

| 术语 | 定义 | 曾用名 |
|---|---|---|
| **KnowledgeBase（知识库）** | 知识的容器；检索策略（indexing_strategy）、Wiki 策略（wiki_config）等以配置形式挂在库上 | knowledge_base + kb_rag_configs + kb_wiki_configs 三者合并 |
| **Knowledge（知识条目）** | 知识库内的一条文档或 FAQ 条目，含来源文件信息、解析状态生命周期（unprocessed→processing→finalizing→completed/failed）、启用状态与自定义元数据 | document + document_revision 两层合并为单条目 |
| **Chunk（切块）** | 知识条目切分出的内容块，可有类型（文本/表格/图像）、父子层级与前后邻接；可被人工编辑，保留原始内容与修订号 | content_chunk（原不可编辑、硬删） |
| **ChunkRevision（块修订）** | 块每次被编辑后留存的不可变历史版本 | —（新增能力） |
| **Embedding（向量记录）** | 切块对应的向量与检索文本副本，独立成表；同一来源唯一 | 原向量内嵌在切块行内 |
| **KnowledgeTag（标签）** | 知识库内的分类标签；一个条目可挂多个标签 | —（新增能力） |
| **TemporaryDocument（临时文档）** | 会话中上传、用完即焚的文档，过期清理 | —（依赖会话域） |
| **VectorStore（向量库）** | 已注册的外部向量引擎实例（pgvector/ES/Milvus 等），知识库可选绑定 | —（原固定 pgvector） |

## 会话与消息

| 术语 | 定义 | 曾用名 |
|---|---|---|
| **Session（会话）** | 一次绑定了知识库与 Agent 的问答上下文，携带检索参数与兜底策略 | —（旧模型无会话，chat 无状态） |
| **Message（消息）** | 会话内的一条发言，含知识引用、执行步骤与渲染内容 | — |

## Agent 与工具

| 术语 | 定义 | 曾用名 |
|---|---|---|
| **CustomAgent** | 用户自定义的智能体（GPTs 式），配置整体以 JSON 表达 | — |
| **McpService / McpToolApproval / McpOAuth*** | 外部工具服务注册、工具级审批开关、OAuth 授权 | — |
| **WebSearchProvider** | Web 搜索提供商配置 | — |

## 渠道与协作

| 术语 | 定义 | 曾用名 |
|---|---|---|
| **ImChannel / ImChannelSession** | IM 平台渠道配置及其与内部会话的映射 | — |
| **EmbedChannel** | 可发布到外部网站的嵌入式对话渠道 | — |
| **Organization（组织）** | 跨租户的共享协作空间 | organization（含义近似，扩展跨租户成员） |
| **KbShare / AgentShare** | 知识库/Agent 向组织分享的授权记录 | kb_shares（含义近似） |

## Wiki

| 术语 | 定义 | 曾用名 |
|---|---|---|
| **WikiPage** | 知识整理产出的页面，归属目录、带双向链接与来源引用（以 JSON 表达） | wiki_page（双向链接与引用从实体表降为 JSON 字段） |
| **WikiFolder** | Wiki 的目录树节点 | wiki_folder（含义不变） |
| **WikiPageRevision** | 页面的不可变版本历史 | —（新增能力；旧模型仅 version 乐观锁） |
| **WikiPageIssue** | 页面质量问题上报 | —（新增能力） |

## 数据源与存储

| 术语 | 定义 | 曾用名 |
|---|---|---|
| **DataSource（数据源）** | 外部内容的同步连接器（webhook/api/db/file），带同步计划与游标 | source（含义近似，扩展同步语义） |
| **SyncLog（同步日志）** | 一次数据源同步的执行统计 | —（原由任务账本承载） |
| **StorageBackend** | 已注册的文件存储后端（local/minio/cos…） | —（原固定 MinIO） |
| **Resource（资源）** | 一个被登记的文件/图像对象，带短句柄、哈希与生命周期 | —（原 storage_key 直连） |
| **ResourceBinding / AccessGrant** | 资源与业务实体的绑定关系 / 限时访问授权 | — |

## 任务与处理

| 术语 | 定义 | 曾用名 |
|---|---|---|
| **PendingOp（待办操作）** | 落库的去重任务队列项，支持认领与过期恢复 | —（原用 Dramatiq+Redis 队列） |
| **DeadLetter（死信）** | 重试耗尽的任务的永久归档，可人工重放 | —（原依赖 Dramatiq DLQ，7 天过期） |
| **ProcessingSpan（处理跨度）** | 文档处理链路的阶段追踪节点，可成树 | processing_span（模型重建，原 runs/spans 两级并为单层跨度树） |

## 用户个性化

| 术语 | 定义 | 曾用名 |
|---|---|---|
| **UserResourceFavorite / UserKbPin** | 用户对资源的收藏 / 对知识库的置顶 | — |
