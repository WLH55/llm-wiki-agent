# Agent Runtime + BYOK + 双 AI 通道

> 状态：Agent/BYOK 方向保留；文中基于 `chunk_refs` 的 Wiki 写入参数属于旧 schema，已由 [ADR-0012](0012-approved-rag-wiki-database-boundaries.md) 的文档引用与原文证据模型取代。

llm_wiki3.0 的 AI 子系统由 **两条通路 + 一个抽象层** 构成：

- **双 AI 通道**（两个入口）：
  - **内置 Agent Runtime**：用户在 Web UI 内直接对话，由系统自带工具集（搜索、图谱遍历、文档检索）支撑。
  - **外部 MCP 通道**：外部 AI 应用（Claude Desktop / Cursor / 其他 Web 应用）通过 HTTP MCP `/mcp` 端点的 `chat` 工具调用（见 [ADR-0004](0004-http-mcp-server.md)）。
- **统一 LLM Client 抽象**（一个底层）：两条通路最终都走同一个 `LLMClient`，屏蔽 OpenAI 协议兼容（OpenAI / Azure / DeepSeek / Qwen / GLM / Kimi 一家抽象）+ Anthropic + Google 三类适配器。
- **BYOK（Bring Your Own Key）**：每个用户在个人设置里填自己的 LLM API Key，加密存储。两条通路的 LLM 调用**都用 BYOK**——外部 MCP 通过 API Key 绑定的 user 找到他的 BYOK。

## Context

PRD v4.2 行 234 P2 提到"双 AI 通道；AI 对话"但没展开。CONTEXT.md 比 PRD 详细——已定义 Agent Runtime / LLM Provider Registry / BYOK 三个术语，但 PRD 没把它写成正式章节。本 ADR 补齐这一层。

## Decision

### 双 AI 通道（两个入口，同一底层）

```
┌──────────────────────┐         ┌──────────────────────┐
│  内置 Agent Runtime    │         │  外部 MCP 通道         │
│  (Web UI 对话)        │         │  (Claude Desktop /    │
│                      │         │   Cursor / 其他)      │
└──────────┬───────────┘         └──────────┬───────────┘
           │                                │
           │  caller = session user         │  caller = API Key 绑定的 user
           │                                │
           └────────────┬───────────────────┘
                        ▼
            ┌─────────────────────────┐
            │  统一 LLMClient 抽象      │
            │  (OpenAI 协议兼容 +      │
            │   Anthropic + Google)    │
            └────────────┬─────────────┘
                         ▼
            ┌─────────────────────────┐
            │  BYOK Key 查找           │
            │  (user_llm_keys 表,加密) │
            └─────────────────────────┘
```

两条通路的差异仅在**入口鉴权方式**（JWT session vs MCP API Key），底层 LLM 调用完全相同。MCP chat 工具不会"AI 套 AI"——它本质是把外部入口转给内置 Agent Runtime 执行。

### BYOK 机制

- **key 归属**：每个 user 在个人设置里填自己的 key（一个 user 可填多个 provider 的 key，如同时有 OpenAI 和 DeepSeek）。
- **加密存储**：用 Fernet 对称加密（密钥派生自 env var `LLM_KEY_ENCRYPTION_KEY`）；DB 里只存密文。
- **查询时解密**：每次 LLM 调用时从 DB 取密文 → 解密 → 用完即丢（不缓存明文）。
- **共享 KB 查询时由查询者的 key 计费**——产品不介入 token 采购/分配/报销，只提供"接入大模型"的能力层。key 来源（公司发 / 自费）是用户与公司之间的私事。

### 嵌入模型 vs LLM 模型分离

KB 创建时绑定**嵌入模型**（参 [ADR-0001](0001-halfvec-multi-dim.md)），与 LLM 模型是两套独立配置：

| 调用场景 | 用谁的 key | 用什么模型 |
|---------|----------|-----------|
| 文档导入时 chunk embedding | 导入者（caller）的 BYOK | KB 绑定的嵌入模型（如 bge-m3） |
| 重嵌入（模型升级时） | 触发重嵌入操作的 caller 的 BYOK | KB 新绑定的嵌入模型 |
| Query embedding（查询向量化） | 查询者（caller）的 BYOK | KB 绑定的嵌入模型 |
| LLM chat（对话） | 查询者（caller）的 BYOK | caller 选的 LLM 模型（如 GLM-4.6） |
| LLM 抽取（实体/概念/综述生成） | 触发抽取的 caller 的 BYOK | caller 选的 LLM 模型 |

**关键约束**：向量检索（pgvector）不需要 key（已嵌入的 chunks 直接查）；但 query embedding 必须有 key——没 key 的用户走 BM25 兜底检索。

### LLM Provider Registry

- **`llm_providers` 表**（admin 维护）：`display_name` / `base_url` / `protocol`（openai / anthropic / gemini）/ `default_models` / `is_active`。
- **默认预置**：OpenAI / Azure / DeepSeek / Qwen / GLM / Kimi / Anthropic / Google 共 8 个 provider。
- **支持自部署模型**：admin 可添加 vLLM / Ollama 等 OpenAI 协议兼容的自部署 endpoint（填 `base_url=http://vllm:8000/v1` + `protocol=openai`）。
- **用户选 provider + 填 key**：`user_llm_keys(user_id, provider_id, encrypted_key, selected_llm_model, is_active)`。

### Agent Runtime 内部工具集

内置 Agent Runtime 的 LLM 可调用以下**系统工具**（不同于 MCP 8 个工具，这些是 Python 函数直接调用，不走 HTTP）：

1. `search_kb(kb_id, query, mode)` — 跨 RAG/Wiki 双路径检索
2. `traverse_graph(kb_id, page_slug, depth)` — 图谱 BFS 邻域
3. `read_page(kb_id, page_slug)` — 读 wiki 页面
4. `read_chunks(kb_id, chunk_ids[])` — 读原始 chunk
5. `write_wiki_page(kb_id, slug, body, chunk_refs)` — 写/更新 wiki 页面（强制 chunk_refs，参 [ADR-0003](0003-three-edge-model.md) + [ADR-0004](0004-http-mcp-server.md) Open Question C）

**不能调用 MCP 工具**——避免循环（MCP chat → 内置 Agent → 调 MCP 工具 → ...）。MCP 工具是给**外部** AI 应用的，内置 Agent 用自己的系统工具。

### 意图分类（零 LLM）—— ❌ 已弃用（2026-07-09）

**原方案**：意图分类走零 LLM（关键词/规则），5 类（`chat` / `search_only` / `summarize` / `compare` / `extract_entities`）路由到不同 prompt + 后处理。

**弃用原因**：grilling 过程中用户决策改为「KB 级别 IndexingStrategy 决定检索能力 + 用户/Agent 显式选检索工具」，不再需要系统根据 query 关键词自动路由。KB 类型由 `knowledge_bases` 表的 4 个布尔开关（`vector_enabled` / `keyword_enabled` / `wiki_enabled` / `graph_enabled`）推断，决定该 KB 能用 `knowledge_search`（路径 B）还是 `wiki_search`（路径 A）还是两者都可。

**替代方案**：详见 [ADR-0009](0009-retrieval-architecture.md) §「KB 类型推断（替代意图分类）」。

## Considered Options

- **A. LLM 通道 + 嵌入通道分（作为"双 AI 通道"的解读）**：rejected as 双 AI 通道含义。LLM 和 embedding 本来就是 `LLMClient` 抽象内的两个 endpoint，不算"两个通道"。用户选 B（内置 + 外部 MCP）。
- **C. BYOK 主 + 系统兜底备**：rejected for default。v4.2 自部署场景下 admin 不应该承担 token 成本（产品不介入 token 采购）；没 key 的用户走 BM25 兜底检索，chat 禁用。**Open Question A**：未来企业版是否提供系统兜底 key？
- **OAuth 模式 key 共享**（共享 KB 用同一 key）：rejected。CONTEXT.md「BYOK」明确"key 来源是用户与公司之间的私事"。

## Consequences

- **schema 新增表**：
  - `llm_providers(id, display_name, base_url, protocol, default_models JSONB, is_active, created_at)`
  - `user_llm_keys(id, user_id, provider_id, encrypted_key TEXT, selected_llm_model, is_active, created_at)` — UNIQUE(user_id, provider_id)
  - `kb_embedding_models(kb_id, provider_id, model_name, embedding_dim)` — KB 创建时绑定（替代/补全 ADR-0001 的 `knowledge_bases.embedding_model_id`）
- **加密存储**：env var `LLM_KEY_ENCRYPTION_KEY`（32 字节，部署时生成）；密文存 DB；每次调用解密。
- **没 key 兜底**：用户没填任何 BYOK key 时——① 向量检索禁用 query embedding，仅走 BM25 关键词检索；② chat / 抽取 / 综述等功能全禁用（前端灰显 + 提示"请在个人设置填 LLM API Key"）。
- **运营成本**：admin 需要预置 8 个 provider 元数据；user 需要被引导填 key（首次使用时弹窗提示）。
- **失去的能力**：跨用户共享 LLM 配额；统一计费/报销（产品定位明确不介入）。

## Open Questions（留给未来 grilling）

- **Open Question A（系统兜底 key）**：未来企业版是否提供系统兜底 key（admin 配额 + 用户共享）？v4.2 P1 不做。
- **Open Question B（重嵌入触发权限）**：KB 模型升级需要全量重嵌入——谁能触发？候选：① 仅 KB owner；② owner + admin；③ 任何 contributor（用各自的 key）。推荐 ①（避免 contributor 误操作烧钱）。
- **Open Question C（key 失效降级）**：用户填的 key 失效（余额耗尽 / 被撤销）时，是中断当前请求 + 提示"key 失效"，还是自动切到用户的另一个 provider key？推荐前者（透明，避免静默成本转移）。

## 参考实现

- LLM Client 抽象：`openai` Python SDK（覆盖 OpenAI 协议兼容的 6 家）+ `anthropic` SDK + `google-generativeai` SDK
- 加密：`cryptography.fernet.Fernet`（密钥派生自 env var）
- BYOK 解密缓存：可选 Redis 缓存（key=user_id+provider_id，TTL=5min），减少 DB 查询；明文不持久化
- 意图分类：Python 关键词正则匹配，无 LLM 调用
