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

**空间（Workspace）**:
共享容器。由创建者（空间 admin）邀请成员加入，可挂载多个 KB。三层 RBAC（L1 空间默认权限 / L2 KB 共享权限 / L3 成员角色）取最小值为生效权限。
_Avoid_: 团队、组织、项目、群组

**OKF（Open Knowledge Format）**:
知识库的可移植捆绑格式（zip）。用于"导出带走"和"导入回来"，不是日常同步通道。
_Avoid_: 备份、快照、同步包

### AI 子系统

**Agent Runtime**:
内置的 AI 子系统。核心是一个 OpenAI 协议兼容的 LLM Client（一家抽象，覆盖 OpenAI / Azure / DeepSeek / Qwen / GLM / Kimi），加 Anthropic / Google 独立适配器。用户在 Web UI 内直接对话，由系统自带工具集（搜索、图谱遍历、文档检索）支撑。
_Avoid_: MCP server、CLI agent、外部 agent（v4.2 已放弃 stdio MCP 接入外部 CLI 工具的路线）

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

**强制工作空间隔离（Mandatory Workspace Isolation）**:
任何用户查询都必须落在一个具体 workspace 上下文中；不存在「跨 workspace 自由搜索」。应用层 RBAC 校验。
_注_: v4.2 暂不做 Postgres RLS——RLS 是企业级兜底，自注册+邀请制场景下应用层 RBAC 已够。RLS 留作未来企业版升级路径。

## v4.1 → v4.2 已弃用术语

| v4.1 术语 | v4.2 状态 | 原因 |
|---|---|---|
| 桌面客户端（Tauri） | 弃用 | 全面 Web 化 |
| 本地 PGLite 引擎 | 弃用 | 数据集中存内网服务器 |
| Rust sidecar（PDF 解析） | 待定 | 解析能力需要回到服务端实现 |
| stdio MCP server | 弃用 | 不再接入外部 CLI |
| 个人模式 / 团队模式（双模式） | 弃用 | 只有"Web 模式"一种 |
