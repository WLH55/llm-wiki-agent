# ADR: 模型 Key 归属从 BYOK 改为工作区级配置

> **Status**: Accepted（2026-08-11，grilling 确认）
> **Supersedes**: [ADR-0006](0006-agent-runtime-byok.md) 的 BYOK（用户级 Key）部分
> **关联 Spec**: 生成集成设计 spec（待写）

## 背景

ADR-0006 原设计 BYOK（Bring Your Own Key）：每个用户在个人设置里填自己的 LLM API Key（Fernet 加密），谁查询谁付费。共享 KB 查询时用查询者的 Key。

WeKnora 生产实践调研（2026-08-11）发现：WeKnora 采用**工作区（Tenant）级模型配置**--admin 配置模型（含加密 API Key），tenant 内所有用户共用。无 per-user Key 概念。models 表用 `parameters JSONB` 承载所有厂商差异配置，api_key 用 AES-256-GCM 加密。KB 通过 `embedding_model_id` + `summary_model_id`（实际是 chat 模型）引用模型 ID。

## 决策

**模型 Key 归属改为工作区级（Tenant-Level），放弃 BYOK。**

### models 表设计（照搬 WeKnora）

```sql
CREATE TABLE models (
    id VARCHAR(64) PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id BIGINT NOT NULL,
    name VARCHAR(255) NOT NULL,
    display_name VARCHAR(255) DEFAULT '',
    type VARCHAR(50) NOT NULL,          -- embedding / chat / rerank / vlm / asr
    source VARCHAR(50) NOT NULL,        -- remote / local
    description TEXT,
    parameters JSONB NOT NULL,          -- base_url/api_key/provider/dimension 等厂商配置
    is_default BOOLEAN DEFAULT false,
    is_builtin BOOLEAN DEFAULT false,
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    deleted_at TIMESTAMPTZ
);
```

- `parameters` JSONB 承载所有厂商差异配置（base_url、api_key、provider、dimension 等）
- `api_key` 在写入 JSONB 前用 **AES-256-GCM** 加密（env `SYSTEM_AES_KEY`），不使用 ADR-0006 原定的 Fernet
- model_type 取值：embedding / chat / rerank / vlm / asr

### KB 模型绑定

```sql
ALTER TABLE knowledge_bases ADD COLUMN embedding_model_id VARCHAR(64) NOT NULL;
ALTER TABLE knowledge_bases ADD COLUMN chat_model_id VARCHAR(64) NOT NULL;
```

- 创建 KB 时 `embedding_model_id` + `chat_model_id` **必填**
- 已有文件的 KB 禁止修改 embedding 模型（维度不兼容）
- 命名用 `chat_model_id`（比 WeKnora 的 `summary_model_id` 更直观）

### MVP 简化

MVP 不做 admin UI 管理模型，通过 env var 配置：
- `CHAT_MODEL_NAME` / `CHAT_API_KEY` / `CHAT_BASE_URL` / `CHAT_PROVIDER`
- `EMBEDDING_MODEL_NAME` / `EMBEDDING_API_KEY` / `EMBEDDING_BASE_URL` / `EMBEDDING_PROVIDER` / `EMBEDDING_DIMENSION`
- 启动时自动写入 models 表（`is_builtin=true`）

### Key 失效处理

| 失败点 | 处理 |
|---|---|
| embedding 模型 Key 失效 | 降级为纯关键词检索（BM25），继续执行 |
| chat 模型 Key 失效 | 返回 SSE `error` 事件，提示"对话模型 Key 失效，请检查系统配置" |
| chat 超时/限流 | 重试 3 次（指数退避）后返回错误提示 |

## 原因

1. **产品定位**：自部署内网服务，团队统一采购 token 比每人各自填 Key 更符合实际使用场景
2. **WeKnora 已验证**：工作区级模型配置在生产环境运行良好，27 个 Provider 自注册
3. **简化 MVP**：admin 配一次，tenant 内所有人可用，不需要每个用户填 Key
4. **BYOK 增加认知负担**：用户要理解"哪个 Provider""填什么 Key""Key 和模型怎么对应"，对内网团队用户不友好

## 后果

- **ADR-0006 的 BYOK 部分被 supersede**：用户级 Key、Fernet 加密、谁查谁付等设计不再适用
- **ADR-0006 的其他部分仍然有效**：Agent Runtime、双 AI 通道、LLM Provider Registry 等架构决策不变
- **新增 models 表**：tenant 级模型管理
- **KB 表变更**：新增 `embedding_model_id` + `chat_model_id` 字段
- **加密方式变更**：Fernet -> AES-256-GCM（与 WeKnora 一致）
- **未来扩展**：P2+ 可加 admin UI 管理模型、YAML 声明式预置模型（WeKnora 同款）
