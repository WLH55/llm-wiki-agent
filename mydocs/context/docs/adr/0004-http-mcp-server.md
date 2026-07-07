# HTTP MCP 工具集

llm_wiki3.0 的 FastAPI 服务暴露 `/mcp` 端点，使用 **Streamable HTTP MCP 协议**（MCP spec 2025-03-26+），让外部 AI 应用（Claude Desktop 通过 mcp-remote 桥接、Cursor、其他 Web 应用）能通过 8 个工具读写知识库。

**API Key 鉴权**：用户在 Web UI 生成 API Key（绑定 user_id + workspace context），MCP 客户端在 `Authorization: Bearer <key>` 里带 key。RBAC 走 [ADR-0002](./0002-tenant-org-rbac.md) 的 fall-through 三步短路。

## Context

CONTEXT.md 的 Agent Runtime 条目原写："_Avoid_: MCP server、CLI agent、外部 agent（v4.2 已放弃 stdio MCP 接入外部 CLI 工具的路线）"——但 PRD US 17/18 明确要做 8 个 MCP 工具。**两个文档直接冲突**。

矛盾根源：CONTEXT.md 当初弃用的是 **stdio MCP**（产品作为 MCP **client** 接入外部 CLI agent，如 gbrain CLI），目的是"不依赖外部 CLI 工具，内置 Agent Runtime"。但 PRD 想要的是反方向——产品作为 MCP **server** **暴露**接口给外部 AI 应用。两个方向被同一句"_Avoid_: MCP server"模糊了。

v4.2 全面 Web 化后：
- **stdio MCP（作为 client）不再需要**——产品自带 Web UI + 内置 Agent Runtime，不依赖外部 CLI 接入。
- **HTTP MCP（作为 server）是天然形态**——FastAPI 服务天然能暴露 HTTP 端点，外部应用通过 HTTP 接入。

## Decision

- **保留 HTTP MCP server**：FastAPI 服务暴露 `/mcp` 端点，使用 Streamable HTTP MCP 协议。
- **8 个工具清单**（与 PRD US 17 一致）：

| # | 工具 | 作用 | 备注 |
|---|------|------|------|
| 1 | `list_kbs` | 列出当前用户可访问的所有 KB（自家 tenant + 共享 organization 挂载的） | 走 RBAC 解析，返回 effective permission |
| 2 | `use_kb(kb_id)` | 设置后续工具调用的默认 KB 上下文（可选优化） | **Open Question A**：HTTP 无状态，每次调用都带 kb_id 才是 source of truth；use_kb 仅是 client-side 便捷 |
| 3 | `list_pages(kb_id, page_type?, folder_id?)` | 列出 wiki 页面（支持 page_type / folder_id 过滤） | 系统页 index/log 排除 |
| 4 | `search(kb_id, query, mode?)` | 跨 RAG/Wiki 双路径检索 | mode: conservative/balanced/tokenmax |
| 5 | `read(kb_id, page_slug)` | 读单个 wiki 页面（含 in_links/out_links/source_refs/chunk_refs） | 返回完整 markdown body |
| 6 | `related(kb_id, page_slug, depth?)` | 邻域查询（ego 模式 BFS） | 走链接图边（无类型），不是类型化关系 |
| 7 | `chat(kb_id, message, history?)` | 对话 | **Open Question B**：让外部 AI 调用我们的 chat = "AI 套 AI"；主要服务非 AI 外部应用（Web 客户端 JS / Slack 机器人） |
| 8 | `update(kb_id, page_slug, body, chunk_refs)` | 写/更新 wiki 页面 | **Open Question C**：US 18 强制要求 chunk_refs，但 LLM 自动生成时可能没有明确原文 chunk 可引 |

## Considered Options

- **B. 完全放弃 MCP server**：rejected。产品价值高（Claude Desktop / Cursor 用户能直接读写知识库），CONTEXT.md 的"弃用"是历史遗留歧义——弃用的是 stdio MCP client 接入，不是 HTTP MCP server 暴露。
- **C. 保留 stdio MCP server**：rejected。与 v4.2 全面 Web 化方向冲突；stdio 需要本地子进程，FastAPI 服务无法直接提供；用户需要双轨运维（Web 服务 + CLI binary），复杂度过高。Claude Desktop 等桌面 IDE 应用通过 mcp-remote 桥接 HTTP MCP 即可接入。
- **HTTP MCP + OAuth 2.1**（MCP spec 推荐）：rejected for default。当前 v4.2 自注册 + 邀请制场景下 API Key 已够；OAuth 2.1 留作未来企业版 / SaaS 多租户场景升级路径。

## Consequences

- **新增 `/mcp` HTTP 端点**：使用 Streamable HTTP MCP 协议（`Content-Type: application/json`，SSE for streaming responses）。FastAPI + Starlette 实现，参考 mcp-python-sdk 的 `fastapi` 适配器。
- **API Key 鉴权**：用户在 Web UI 生成 API Key（绑定 user_id + workspace context）。MCP 客户端在 `Authorization: Bearer <key>` 里带 key。
- **RBAC 上下文**：API Key 绑定时确定 workspace context（tenant / organization）。即用户生成 key 时选"这个 key 代表我在 X 组织的视角"，后续工具调用都按这个 context 走 fall-through 三步短路。
- **工具 schema**：8 个工具的 input/output schema 用 Pydantic 定义，自动生成 MCP tool manifest（JSON Schema）。
- **失去的能力**：无 stdio MCP——Claude Desktop / Cursor 等桌面 IDE 应用无法直接接入，用户需要配置 mcp-remote 桥接（用户文档需写明）。
- **运营成本**：需要维护 MCP spec 兼容性（spec 仍在演进）；需要写"MCP 接入指南"列出常见客户端配置。

## Open Questions（留给下一轮 grilling）

- **Open Question A（`use_kb` 语义）**：HTTP 无状态，每次调用都带 kb_id 才是 source of truth。`use_kb` 只是 client-side 便捷（"我后续调用默认用这个 KB"），不是 server-side session 状态。候选方案：① 保留但明确文档说明（推荐）；② 砍掉 `use_kb`，所有工具调用强制带 kb_id；③ 保留且实现 server-side session（增加复杂度，不推荐）。
- **Open Question B（`chat` 工具的"AI 套 AI"）**：让外部 AI（如 Claude Desktop）调用我们的 chat 工具 = 外部 AI 把请求转给我们内置 LLM，多一层延迟 + token 成本。但如果是给"非 AI 外部应用"（Web 客户端 JS / Slack 机器人）用的，就有意义。候选方案：① 保留 chat 工具，文档明确"主要服务非 AI 外部应用"（推荐）；② 砍掉 chat 工具，外部 AI 应该用 search + read + update 自己组合；③ 保留且加 metadata 标注调用方类型。
- **Open Question C（`update` 强制 chunk_refs）**：US 18 强制要求，但 LLM 自动生成综述性内容时可能没有明确原文 chunk 可引。候选方案：① 强制要求 `chunk_refs` 非空（按 US 18 原文，可能过度约束）；② 允许 `chunk_refs: []` 但记录到 process_log 标记"无溯源"，治理时追责（推荐）；③ 改为软警告，不强制。

## 参考实现

- MCP spec：https://modelcontextprotocol.io/specification（Streamable HTTP transport 2025-03-26+）
- mcp-python-sdk：`mcp.server.fastapi` 适配器
- mcp-remote：https://github.com/geelen/mcp-remote（Claude Desktop / Cursor 桥接 HTTP MCP）
- 8 个工具的 input/output schema：用 Pydantic BaseModel 定义，`mcp.server.fastapi` 自动生成 manifest
