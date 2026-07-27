# MVP 范围与砍点决策

> 状态：MVP 范围方向保留；“schema 预留但不实现”章节中的页面数组、物化路径、`content_chunks.chunk_type` / `wiki_page_id` 等旧字段已由 [ADR-0012](./0012-approved-rag-wiki-database-boundaries.md) 取代。

llm_wiki3.0 的 MVP（P1）**聚焦双路径核心闭环**，鉴权与扩展性决策**极简**，把工程精力集中到检索模块质量上。前面 7 个 ADR（0001-0007）描述的是**长期架构方向**——MVP 只实现其中**核心子集**，但 schema 按 ADR 设计以避免未来 migration。

## Context

前面 7 个 ADR（halfvec 多维度 / 两层 RBAC / 三套边 / HTTP MCP / 自注册邀请 / BYOK 双 AI 通道 / 多源挂载）描述了完整架构。但 MVP 阶段如果全部实现，工程量过大且偏离核心价值主张。

**核心价值主张**（PRD 行 82）：双路径分离（RAG + Wiki）——这是产品差异化，**砍不得**。

**MVP 决策原则**：
1. 双路径核心闭环必须完整（RAG 检索 + Wiki 抽取 + chat + 手动编辑）。
2. 鉴权极简（bootstrap owner + 系统兜底 key），未来扩展到多 user / BYOK 不需要重写。
3. schema 按 ADR 设计（预留 tenant_id / organizations / kb_shares / sources.source_type / llm_providers / user_llm_keys 等表/列），但**功能不实现**——P2+ 启用即可。
4. 检索模块的工程质量是 MVP 的核心交付物：RAG 内部完成向量 + BM25 + RRF，Wiki 检索独立完成；不在 MVP 融合两条路径。

## Decision

### MVP（P1）实现的 6 个模块

| # | 模块 | MVP 范围 | 长期 ADR |
|---|------|---------|---------|
| 1 | KB 创建 | 默认绑定 bge-m3（1024 维），用户无需选 | [ADR-0001](./0001-halfvec-multi-dim.md) |
| 2 | 文档上传 + 解析 + 分块 + 嵌入 | manual only；Python worker + Redis；CJK 300 词分块 | [ADR-0007](./0007-multi-source-mounting.md) |
| 3 | **检索（双路径独立）** | IndexingStrategy 四开关 + 路径 A wiki_search（正则+字段权重）+ 路径 B 原文 chunk 的向量+BM25+RRF；Wiki 不写入 RAG、不 boost；**工程质量核心** | [ADR-0010](./0010-mvp-wiki-rag-separation.md) |
| 4 | LLM chat | 内置 Agent + 单 provider（env var）+ 引用回链 chunks | [ADR-0006](./0006-agent-runtime-byok.md) |
| 5 | LLM 抽取实体/概念 → wiki_pages + `[[xxx]]` 链接图边 | 链接图边 MVP 必做；目录树 + 物化路径缓存 P2 | [ADR-0003](./0003-three-edge-model.md) |
| 6 | wiki 页手动编辑 + last-write-wins | version 字段乐观锁；冲突 409 | [ADR-0003](./0003-three-edge-model.md) |

### MVP（P1）的鉴权极简

- **bootstrap owner**：env var `BOOTSTRAP_OWNER_EMAIL` + `BOOTSTRAP_OWNER_PASSWORD` 启动时创建唯一 owner；不做自注册。
- **JWT session**：HS256，24h 有效期；**不做 refresh token**（过期重登）；**不做 workspace context 切换**（只有一个 space）。
- **系统兜底 LLM key**：env var `LLM_API_KEY` + `LLM_PROVIDER=glm`（admin 配置一个）；用户**可选**填自己的 BYOK key 覆盖（schema 已支持 `user_llm_keys` 表）。
- **不做**：自注册 / 邀请制 / 多 user / 多 provider / 组织 / kb_shares / MCP server。

### MVP（P1）schema 预留但不实现

为避免 P2 扩展时 migration，以下表/列 MVP 阶段就创建（空表 ready）：

| 表/列 | MVP 状态 | P2 启用条件 |
|-------|---------|-----------|
| `knowledge_bases.tenant_id` | 创建列 + 默认值 = bootstrap owner 的 tenant_id | P2 多 user 时按 caller 写入 |
| `pages.tenant_id` / `content_chunks.tenant_id` / `sources.tenant_id` 等 | 同上 | 同上 |
| `organizations` / `org_members` / `kb_shares` | 创建空表 | P2 启用邀请制 + 共享 |
| `org_invites` / `password_resets` | 创建空表 | P2 启用自注册 + 邀请 |
| `sources.source_type` 列 | 创建列 + 只实现 manual adapter | P3 加 RSS / Yuque / Feishu 等 adapter |
| `llm_providers` 表 | 预置 1 条（admin env var 配置的 provider，如 GLM） | P2 开放多 provider（预置 8 个） |
| `user_llm_keys` 表 | 创建空表 | P2 开放 BYOK |
| `pages.folder_id` / `parent_slug` / `category_path` / `depth` / `wiki_path` | 创建列 + 默认空 | P2 启用目录树（folder_id 写入 + 物化路径重算） |
| `wiki_folders` 表 | 创建空表 | P2 启用目录树 |
| `kb_embedding_models` 表 | MVP 用 `knowledge_bases.embedding_model_id` 简化字段即可 | P2 多嵌入模型时启用完整表 |
| `content_chunks.chunk_type` / `wiki_page_id` | 创建列；MVP 只写原文 chunk，`wiki_page_id` 恒为 NULL | 独立评测完成并通过融合 ADR 后启用 Wiki chunk 写入 |
| `wiki_pages.source_refs` / `chunk_refs` / `version` | 创建列并维护 Wiki 到原文的证据血缘；不据此生成 Wiki chunk | 未来做血缘去重、索引失效和一手证据回链 |

### MVP（P1）完全不做的（无 schema 预留）

- **MCP server**（[ADR-0004](./0004-http-mcp-server.md)）：P3 才加，schema 无预留（直接加 `/mcp` 端点 + MCP API Key 表）。
- **意图分类**（[ADR-0006](./0006-agent-runtime-byok.md) §意图分类）：P2 才加，纯 Python 关键词规则，无需 schema。
- **MD 导出包**：P3 才加，无 schema 改动（运行时序列化 wiki_pages 为 markdown zip）。
- **多模态**（VLM OCR / Caption）：P4 才加。
- **OKF**：[ADR-0005 弃用决策](../CONTEXT.md#知识资产)，永久不做。

## Considered Options

- **激进 MVP（只做 RAG 路径）**：rejected。Wiki 路径是产品差异化核心；砍掉只剩"另一个 RAG 工具"，失去存在意义。用户明确选"Wiki 和 RAG 两个都是 MVP"。
- **保守 MVP（含多 user + 邀请制）**：rejected。鉴权流程（自注册 / 邮箱验证 / 邀请 token / workspace context 切换）会消耗大量工程时间，偏离核心价值。MVP 用 bootstrap owner + 单 user 已够验证产品价值。
- **不预留 schema（P2 时再加）**：rejected。预留 tenant_id 列成本几乎为零；P2 加多 user 时如果业务表没 tenant_id 列，需要 ALTER TABLE 大表（chunks 可能百万行），锁表风险高。
- **MVP 用 SQLite 而非 Postgres**：rejected。pgvector 不支持 SQLite；MVP 就要用 pgvector 才能验证向量检索质量。

## Consequences

- **工程量大幅缩减**：MVP 砍掉了约 60% 的 ADR 决策（多 user / 邀请 / MCP / 多 provider / 多源 / 目录树 / 意图分类），6 个核心模块可聚焦质量。
- **检索模块是 MVP 的核心交付物**：RAG 路径的混合搜索稳定性（中英混排 + RRF）与 Wiki 路径的结构化检索分别评测；跨路径 Boost 和联合排序延后。
- **schema 预留的代价**：业务表多了一些默认值列（`tenant_id` 默认 bootstrap owner 的 ID），代码层需要从 env var 读 bootstrap owner → 创建 tenant → 业务表默认 tenant_id。可接受。
- **失去的能力（MVP 阶段）**：
  - 多人协作（只有 bootstrap owner 一人）
  - 外部 AI 应用接入（无 MCP）
  - 多模型 / 多 provider 选择（只有 env var 配的一个）
  - 多源（只有 manual）
  - 目录树（只有 wiki_path 简单排序）
  - 意图分类（所有 query 都走 chat）
- **P2 扩展路径清晰**：每个延后的 ADR 决策都有明确的"启用条件"——只需要业务代码改动 + 数据回填（如多 user 启用时把历史数据 tenant_id 全设为 bootstrap owner 的 tenant_id），不需要 schema migration。

## Open Questions（留给未来 grilling）

- **Open Question A（MVP 的 chat 是否做 streaming）**：✅ **已决策（2026-07-09）**——MVP 就做 streaming（SSE）。用户体验上 streaming 是 chat 的标配，不做会让 MVP 评审减分；工程复杂度（SSE 长连接 + 前端 EventSource + LLM 流式拼接）可接受。
- **Open Question B（MVP 的检索结果 UI）**：✅ **已修订（2026-07-27）**——不做双路径联合排序 UI。`wiki_search` 独立检索 `wiki_pages`；`knowledge_search` 只检索原文 `content_chunks`。Wiki 页面不写入 RAG、不做 1.3 倍加权；详见 [ADR-0010](./0010-mvp-wiki-rag-separation.md)。

## 参考实现

- bootstrap owner：FastAPI startup event 读 env var → 创建 user + tenant（如果不存在）
- 系统兜底 LLM key：env var `LLM_API_KEY` + `LLM_PROVIDER`；优先级低于 `user_llm_keys`（如果用户填了自己的 key 则用用户的）
- 检索模块：pgvector + PG 全文（zhparser 中文分词）+ Python RRF 融合实现
