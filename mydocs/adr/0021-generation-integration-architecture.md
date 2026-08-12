# ADR: 生成集成架构（插件化流水线 + XML 上下文 + 编号引用 + SSE）

> **Status**: Accepted（2026-08-11，grilling 确认）
> **关联 ADR**: [ADR-0020](0020-tenant-level-model-config.md)（工作区级模型配置）
> **关联 Spec**: 生成集成设计 spec（待写）

## 背景

本项目后端目前是纯检索器--检索 API 直接返回 ChunkHit 列表给前端，**没有 LLM 生成答案这一环**（RAG 的 "G" 完全缺失）。P0（检索地基 spec）只覆盖了检索链路，P1 需要补上生成集成。

WeKnora 生产实践调研（2026-08-11）发现：WeKnora 用插件化 chat_pipeline（EventManager + Plugin，10 个事件），XML 结构化上下文，双层句柄引用回链，SSE 流式输出。

## 决策

### 1. 插件化流水线（EventManager + Plugin 骨架）

MVP 搭好插件化骨架，后续 rerank、查询重写、CRAG 都是新 Plugin。

- **EventManager**：按事件序列编排，依次触发每个事件
- **Plugin**：实现 `on_event(event, context)` 接口，只处理自己那个事件
- **ChatContext**：上下文字典，Plugin 之间通过它传递状态（query、kb_id、chunks、prompt、answer、citations）

### 2. MVP 事件序列（5 个）

```
SEARCH -> FILTER_TOP_K -> INTO_CHAT_MESSAGE -> GENERATE -> FORMAT_CITATIONS
```

| 事件 | 作用 | Plugin |
|---|---|---|
| SEARCH | 调用检索逻辑（vector + bm25 + RRF + nearby）获取 chunks | SearchPlugin |
| FILTER_TOP_K | 按 LLM 上下文窗口截断到 top-K（默认 5） | FilterTopKPlugin |
| INTO_CHAT_MESSAGE | chunks 渲染为 XML 结构化上下文 + 分配 citation_id | IntoChatMessagePlugin |
| GENERATE | 调 LLM 生成答案（SSE 流式），严格模式 Prompt | GeneratePlugin |
| FORMAT_CITATIONS | 提取 [N] 标注，查回 chunk 元数据，组装 citations 列表 | FormatCitationsPlugin |

**骨架预留但 MVP 不注册 Plugin 的事件位**：QUERY_UNDERSTAND（SEARCH 前）、CHUNK_RERANK（SEARCH 后）、CHUNK_MERGE（RERANK 后）、LOAD_HISTORY（最前）。

### 3. XML 结构化上下文

INTO_CHAT_MESSAGE 把检索结果渲染为 XML：

```xml
<documents>
  <document id="1" title="产品规格书" source="manual">
    <context id="1">产品型号为 X-100，支持 5G 网络...</context>
  </document>
</documents>
```

### 4. 编号引用（简化版，非双层句柄）

- 上下文里 `<context id="1">` 编号
- LLM 输出 `[1]` 标注引用来源
- FORMAT_CITATIONS 提取标注，查回 chunk 元数据
- 通过 SSE `done` 事件补发 citations 列表（流后补发，非流中解析）
- 前端用 citations 列表把 `[1]` 渲染为可点击引用卡片

### 5. 严格模式 Prompt + 无结果兜底

系统 Prompt 要求 LLM 只基于检索上下文回答，禁止先验知识。检索无结果时不调 LLM，直接返回"根据知识库中的信息，无法回答该问题。"

### 6. SSE 流式输出

```
event: token
data: {"text": "该产品型号为 X-100 [1]"}

event: done
data: {"citations": [{"id": 1, "title": "产品规格书", "source": "manual", "chunk_id": 123}]}
```

### 7. MVP 纯单轮

不做对话历史、不做指代消解。每次 chat 请求独立。`LOAD_HISTORY` 事件位预留，未来加多轮只需注册 Plugin。

### 8. 检索接口重新设计

旧 search API（`search/api/routes.py`）丢弃。检索逻辑内聚到 SearchPlugin。`ChunkHit` schema 替换为 `RetrievalResult`（含 document_title / source_type / source_locator / citation_id 等字段）。

### 9. chat API 端点

```
POST /api/v1/kb/{kb_id}/chat
Content-Type: application/json
Accept: text/event-stream

请求体: {"query": "...", "limit": 5}
SSE 响应: token 事件流 -> done 事件（含 citations） / error 事件
```

## Considered Options

- **A. 简单函数调用（无插件化）**：rejected。后续加 rerank/查询重写要改核心函数
- **B. 插件化流水线**（Selected）：早搭骨架，后续每个新能力是一个 Plugin
- **C. 中间路线（阶段函数 + context dict）**：rejected。用户选择 B，理由是插件化迟早要做
- **Markdown 上下文**：rejected。多文档区分不清晰、引用标注易出错
- **双层句柄引用**：rejected。MVP 过重（内网服务无 chunk_id 泄漏风险）
- **宽松模式 Prompt**：rejected。幻觉风险大，RAG 核心价值是可信溯源
- **非流式返回**：rejected。PRD v4.2 MVP 明确要求 SSE 流式
- **流中引用解析**：rejected。`[` 刚出现还没到 `1]` 的中间状态处理复杂，流后补发更简单
- **多轮对话**：rejected for MVP。单轮先跑通全链路，骨架预留 LOAD_HISTORY

## 后果

- **新增 chat 模块**：`backend/app/chat/`（pipeline + plugins + schemas）
- **丢弃旧 search API**：`backend/app/search/api/` 废弃，检索逻辑迁入 SearchPlugin
- **ChunkHit -> RetrievalResult**：数据结构重命名 + 字段扩充
- **新增 models 表**：见 [ADR-0020](0020-tenant-level-model-config.md)
- **KB 表变更**：新增 embedding_model_id + chat_model_id
- **测试 UI 重设计**：原"文档摄入测试 UI"改用 chat API 验证
- **未来扩展**：P3 加 CHUNK_RERANK Plugin（cross-encoder）、QUERY_UNDERSTAND Plugin（查询重写）；P2 加 LOAD_HISTORY Plugin（多轮对话）
