# WeKnora 多租户与共享空间架构文档

> 本文档系统整理 WeKnora 的多租户领域模型：Tenant（租户/工作空间）与 Organization（共享空间）双层结构、资源归属规则、跨租户共享机制、API Key 解析链路、资产传承语义，以及关键的设计权衡。
>
> 适用于想要理解、扩展或调试多租户、共享空间、跨租户访问逻辑的开发者。
>
> 术语定义见 `CONTEXT.md` 的 "Multi-tenant layer" 章节。本文档解释"为什么这么设计"。

---

## 目录

- [1. 概述](#1-概述)
- [2. 双层空间模型](#2-双层空间模型)
  - [2.1 Tenant（工作空间）—— 资源归属边界](#21-tenant工作空间--资源归属边界)
  - [2.2 Organization（共享空间）—— 跨租户协作载体](#22-organization共享空间--跨租户协作载体)
  - [2.3 二者对比](#23-二者对比)
- [3. 为什么不是"群聊模型"](#3-为什么不是群聊模型)
  - [3.1 候选方案：纯 Org 模型](#31-候选方案纯-org-模型)
  - [3.2 在公司内部场景下的 5 个失败点](#32-在公司内部场景下的-5-个失败点)
  - [3.3 决策结论](#33-决策结论)
- [4. 数据模型](#4-数据模型)
  - [4.1 核心表关系图](#41-核心表关系图)
  - [4.2 tenants（资源归属真相源）](#42-tenants资源归属真相源)
  - [4.3 tenant_members（租户内成员）](#43-tenant_members租户内成员)
  - [4.4 organizations（跨租户协作载体）](#44-organizations跨租户协作载体)
  - [4.5 organization_tenant_members（按租户加成员）](#45-organization_tenant_members按租户加成员)
  - [4.6 kb_shares / agent_shares（共享指针）](#46-kb_shares--agent_shares共享指针)
- [5. 角色体系与 3-D 上限规则](#5-角色体系与-3-d-上限规则)
  - [5.1 双角色体系](#51-双角色体系)
  - [5.2 3-D 上限规则](#52-3-d-上限规则)
- [6. 跨租户 Key 解析链路](#6-跨租户-key-解析链路)
  - [6.1 Model 可见性规则](#61-model-可见性规则)
  - [6.2 三条 effectiveTenantID 切换路径](#62-三条-effectivetenantid-切换路径)
  - [6.3 端到端调用链：Bob 通过共享 Agent 访问 Alice 的 KB](#63-端到端调用链bob-通过共享-agent-访问-alice-的-kb)
- [7. 共享机制详解](#7-共享机制详解)
  - [7.1 共享 KB（kb_shares）](#71-共享-kbkb_shares)
  - [7.2 共享 Agent（agent_shares）](#72-共享-agentagent_shares)
  - [7.3 三步访问解析](#73-三步访问解析)
- [8. 资产传承语义](#8-资产传承语义)
  - [8.1 Tenant 内成员被踢](#81-tenant-内成员被踢)
  - [8.2 Org 内租户被移除](#82-org-内租户被移除)
  - [8.3 资产传承规则总结](#83-资产传承规则总结)
  - [8.4 已知清理缺口](#84-已知清理缺口)
- [9. 邀请与加入流程](#9-邀请与加入流程)
  - [9.1 Tenant 邀请（加入工作空间）](#91-tenant-邀请加入工作空间)
  - [9.2 Organization 邀请（加入共享空间）](#92-organization-邀请加入共享空间)
  - [9.3 OIDC SSO 自动建租户](#93-oidc-sso-自动建租户)
- [10. 关键设计权衡](#10-关键设计权衡)
- [11. 关键文件索引](#11-关键文件索引)

---

## 1. 概述

WeKnora 是一个 **多租户知识库平台**。多租户不是 SaaS 套话，而是这套系统的核心架构决策：

- **资源有归属**：每个 KB、Model、Agent、Chunk 都属于一个且仅一个 Tenant
- **协作跨归属**：成员需要读别人的 KB、用别人的 Agent，但不能改变其归属
- **Key 有归属**：每次 LLM 调用消耗的 API Key 额度，归属到资源所有者的 Tenant，而不是调用者个人

为了同时满足这三点，WeKnora 采用 **双层空间模型**：

| 层 | 名字 | UI 叫法 | 角色 |
|---|------|---------|------|
| 内层 | Tenant | "工作空间" | 资源归属边界（账户） |
| 外层 | Organization | "共享空间" | 跨租户协作载体（通道） |

**核心特征**：
- 资源（KB / Agent / Model）**始终属于一个 Tenant**，永不"移动"
- Organization 不持有资源，只持有 **共享指针**（`kb_shares` / `agent_shares`）
- 跨租户访问时，中间件切换 `EffectiveTenantID`，让检索/Key 解析命中源租户

---

## 2. 双层空间模型

### 2.1 Tenant（工作空间）—— 资源归属边界

Tenant 是 **账户级别的概念**。代码定义见 `internal/types/tenant.go:86`：

```go
type Tenant struct {
    ID                  uint64
    Name                string
    APIKey              string                 // AES-256 加密存储
    StorageQuota        int64                  // 默认 10GB
    StorageUsed         int64
    RetrieverEngines    RetrieverEngines       // 检索引擎配置
    ContextConfig       *ContextConfig         // 全局 LLM 上下文配置
    StorageEngineConfig *StorageEngineConfig   // 存储引擎配置（Local/MinIO/COS/...）
    ParserEngineConfig  *ParserEngineConfig    // 文档解析引擎
    Credentials         *CredentialsConfig     // 第三方凭证
    RetrievalConfig     *RetrievalConfig       // 检索参数
    // ...
}
```

**关键字段**：`APIKey`、`StorageQuota`、`StorageEngineConfig` —— 这些字段 **Organization 没有**。这就是 Tenant 是"账户"的代码铁律。

资源归属铁律（5 条）：

1. **`knowledge_bases.tenant_id`** —— KB 属于一个 Tenant
2. **`models.tenant_id` + `is_builtin`** —— Model 要么属于一个 Tenant，要么是全局 builtin（`tenant_id=10000`）
3. **`custom_agents.tenant_id`** —— Agent 属于一个 Tenant
4. **`tenants.storage_quota` / `storage_used`** —— 配额和用量按 Tenant 计算
5. **`tenants.api_key`** —— API Key、AES 加密凭证挂在 Tenant 上

### 2.2 Organization（共享空间）—— 跨租户协作载体

Organization 是 **通道级别的概念**。代码定义见 `internal/types/organization.go:61`：

```go
type Organization struct {
    ID                      string
    Name                    string
    OwnerID                 string
    OwnerTenantID           uint64    // 不可改、不可删（Plan 3 #1303）
    InviteCode              string
    InviteCodeExpiresAt     *time.Time
    RequireApproval         bool
    Searchable              bool      // 是否可被搜索发现
    MemberLimit             int       // 默认 50
    // ... 没有 APIKey / StorageQuota / 任何资源字段
}
```

**关键缺失字段**：没有 `APIKey`、没有 `StorageQuota`、没有 `RetrieverEngines`。这就是 Organization 不是"账户"的代码铁律 —— 它无法独立持有资源。

**OwnerTenantID 的特殊性**：migration 000046 之后，这个字段不可改、不可删。即使 Owner 用户后续切换租户或被软删除，Organization 也不会成为孤儿 —— Owner 所属的原始 Tenant 永远是其"托管者"。

### 2.3 二者对比

| 维度 | Tenant（工作空间） | Organization（共享空间） |
|------|-------------------|------------------------|
| **本质** | 资源归属（账户） | 协作通道 |
| **持有资源** | ✅ KB/Model/Agent/Chunk 全部 | ❌ 一切资源都不持有 |
| **API Key** | ✅ `tenants.api_key` | ❌ 无 |
| **存储配额** | ✅ `storage_quota` / `storage_used` | ❌ 无 |
| **成员单位** | 单个 User（`tenant_members.user_id`） | 整个 Tenant（`organization_tenant_members.tenant_id`） |
| **角色体系** | Owner/Admin/Contributor/Viewer（4 级） | Admin/Editor/Viewer（3 级） |
| **创建主体** | OIDC 自动建 + 用户自助建 | 任意用户自助建 |
| **删除语义** | 删除则资源全部级联删除 | 删除则只孤儿化共享记录，资源不动 |

---

## 3. 为什么不是"群聊模型"

在内部讨论中曾提出一个替代方案：**只保留 Organization 一层**，每个部门负责人建一个 Org，邀请部门成员进来，成员各自配 Key、各自共享 KB，类比微信群聊模型。这个方案最终被否决。本节记录决策依据。

### 3.1 候选方案：纯 Org 模型

```
Alice 自助注册 → 没有"个人空间"，必须加入某个 Org 才能用
Alice 想分享 KB → 共享到 Org
Alice 配 API Key → Key 跟 Alice 个人绑定，Alice 离开则 Key 失效
Org 群主 → 可以转交，类似微信群主
```

### 3.2 在公司内部场景下的 5 个失败点

**失败点 1：公司资产被员工"个人 Key"绑定**

设想：财务部 50 个 KB，全部用财务员工 Alice 的个人 API Key 配置。Alice 离职 → 50 个 KB 全部失效。换 Key 需要逐个 KB 重配。

 Tenant 模型下：财务部 Tenant 持有 Key，Alice 只是 Tenant 的一个 Contributor/Admin，Alice 离职不影响 Key。

**失败点 2：存储配额无法落地**

Wiki 子系统、文档摄入、向量索引都会产生存储成本。群聊模型下，"群存储"由谁付？只能按个人算 → 个人离职后该删谁的？配额管理变成噩梦。

Tenant 模型下：每个 Tenant 有 `storage_quota`，所有 KB/文档/向量都计入 `storage_used`，账单清晰。

**失败点 3：财务/审计无法归因**

LLM 调用消耗真金白银。群聊模型下，"这条查询用了谁的 Key"需要追溯个人，跨人协作时计费归属混乱。

Tenant 模型下：每次调用归属到 `EffectiveTenantID` 对应的 Tenant，月末按 Tenant 出账单。

**失败点 4：合规边界难以表达**

公司某些数据（HR、财务、源代码）必须留在公司 controlled 边界内。群聊模型下，员工把"群"转给外部人员、把 KB 共享给非公司 Org —— 几乎无法阻止。

Tenant 模型下：Tenant 是公司资产边界，Owner/Admin 在公司侧控制，外部人员无法成为 Owner。

**失败点 5：跨 Org 资源传承缺失**

一个 KB 在 Org A 共享过、又在 Org B 共享过。Alice 离职后，这两个共享关系归谁？群聊模型没有答案。

Tenant 模型下：KB 始终在 Alice 所属的 Tenant 里。Alice 被 Tenant 移除 → KB 留在 Tenant，Owner/Admin 可重新指派 CreatorID 或继续使用。

### 3.3 决策结论

**保留 Tenant 层**。Organization 作为跨租户协作的轻量载体存在，但**不能替代 Tenant**。

这并不是说群聊模型在所有场景都不行 —— 在"个人优先 (Personal-first)"的 C 端工具（Notion 个人版、飞书文档个人版）里它能跑通。但在 **公司内部知识库** 这种"组织优先 (Org-first)"场景里，没有 Tenant 层会导致上述 5 个问题无解。

---

## 4. 数据模型

### 4.1 核心表关系图

```
┌──────────────────────────────┐
│         users                │
│  id (PK)                     │
│  tenant_id (home tenant)     │  ────┐
└──────────────────────────────┘      │
        │                             │
        │ 1:N                         │
        ▼                             │
┌──────────────────────────────┐      │     ┌──────────────────────────────┐
│       tenant_members         │      │     │         tenants              │
│  user_id (FK)                │      ├────▶│  id (PK)                     │
│  tenant_id (FK)              │      │     │  api_key (encrypted)         │
│  role (owner/admin/          │      │     │  storage_quota / used        │
│         contributor/viewer)  │      │     │  retriever_engines           │
│  status (active/invited/     │      │     │  storage_engine_config       │
│          suspended)          │      │     │  ...                          │
└──────────────────────────────┘      │     └──────────────────────────────┘
                                      │                     ▲
                                      │                     │ owns
                                      │                     │
                        ┌─────────────┴─────────┐           │
                        │                       │           │
                        ▼                       ▼           │
              ┌──────────────────┐    ┌──────────────────┐  │
              │ knowledge_bases  │    │   custom_agents  │  │
              │  id (PK)         │    │   id (PK)        │  │
              │  tenant_id (FK) ─┼────┼── tenant_id (FK) ─┼──┤
              │  creator_id      │    │   config (json)  │  │
              │  embedding_model │    │   ...             │  │
              │  summary_model   │    └──────────────────┘  │
              └──────────────────┘            ▲              │
                        ▲                     │              │
                        │ shared via          │ shared via   │
                        │                     │              │
┌──────────────────────────────┐      ┌──────────────────────────────┐
│         kb_shares            │      │       agent_shares           │
│  kb_id (FK)                  │      │  agent_id (FK)               │
│  organization_id (FK)        │      │  organization_id (FK)        │
│  source_tenant_id (FK) ◀─────┼──────┤  source_tenant_id (FK) ◀─────┤
│  permission (admin/editor/   │      │  permission (admin/editor/   │
│             viewer)          │      │             viewer)          │
└──────────────────────────────┘      └──────────────────────────────┘
                ▲                                  ▲
                │ point into                       │ point into
                │                                  │
                └──────────┐    ┌──────────────────┘
                           ▼    ▼
              ┌──────────────────────────────┐
              │       organizations          │
              │  id (PK)                     │
              │  owner_id (user)             │
              │  owner_tenant_id ◀─── 不可改  │
              │  invite_code                 │
              │  searchable / require_approval│
              │  ...                          │
              └──────────────────────────────┘
                           ▲
                           │ N:M via
                           │
              ┌──────────────────────────────┐
              │ organization_tenant_members  │
              │  organization_id (FK)        │
              │  tenant_id (FK) ◀── 加成员单位是 Tenant  │
              │  role (admin/editor/viewer)  │
              │  representative_user_id       │ ◀── 仅用于 UI/审计
              └──────────────────────────────┘
```

### 4.2 tenants（资源归属真相源）

参见 `internal/types/tenant.go:86-125`。关键点：

- `api_key` 通过 `BeforeSave` AES-256-GCM 加密落盘，`AfterFind` 解密读出
- `storage_quota` 默认 `10737418240`（10GB），`storage_used` 实时累加
- `retriever_engines` 是 JSONB，未配置时回落到 `RETRIEVE_DRIVER` 环境变量
- 软删除：`deleted_at` 字段保留审计轨迹

### 4.3 tenant_members（租户内成员）

参见 `internal/types/tenant_member.go:86-107`。关键点：

- `(user_id, tenant_id)` 是逻辑唯一键（partial unique index `uniq_user_tenant`）
- `role` 默认 `contributor`，4 级：`owner (40) / admin (30) / contributor (20) / viewer (10)`
- `status`：`active` 才被 auth 中间件认账；`invited` 等待接受；`suspended` 是 admin 撤销
- `invited_by` 记录邀请人，自助注册的行此字段为 NULL

### 4.4 organizations（跨租户协作载体）

参见 `internal/types/organization.go:61-102`。关键缺失字段：

- **没有** `api_key`
- **没有** `storage_quota` / `storage_used`
- **没有** `retriever_engines`

唯一资源类字段：`owner_id`（用户级）、`owner_tenant_id`（租户级，不可改）。

### 4.5 organization_tenant_members（按租户加成员）

参见 `internal/types/organization.go:115-127`。Plan 3 (#1303) 把成员单位从 User 提升到 Tenant：

```go
type OrganizationTenantMember struct {
    OrganizationID       string        // 哪个 Org
    TenantID             uint64        // 哪个 Tenant 加入了
    Role                 OrgMemberRole // 该 Tenant 在 Org 中的角色
    RepresentativeUserID string        // 仅 UI/审计用，不参与权限判断
    // ...
}
```

**为什么按 Tenant 而不是按 User**：因为权限传递是基于 Tenant 的（一个 Tenant 的成员都能访问该 Tenant 共享进来的资源），按 User 加成员会导致权限计算复杂且不可表达"整个部门加入"的语义。

### 4.6 kb_shares / agent_shares（共享指针）

参见 `internal/types/organization.go:196-255`。关键点：

```go
type KnowledgeBaseShare struct {
    KnowledgeBaseID string        // 共享的 KB
    OrganizationID  string        // 共享到哪个 Org
    SharedByUserID  string        // 谁发起的共享
    SourceTenantID  uint64        // KB 的源 Tenant（用于跨租户 Key 解析）
    Permission      OrgMemberRole // 授予 Org 的角色上限
}
```

**共享不改变归属**：`kb_shares` 行的存在不修改 `knowledge_bases.tenant_id`。一个 KB 共享到 5 个 Org，仍然只属于 1 个 Tenant。

`agent_shares` 同形，但 Agent 的绑定 KB 跟随 Agent 一起"以只读方式"出现在 Org 中（不创建独立的 `kb_shares` 行）。

---

## 5. 角色体系与 3-D 上限规则

### 5.1 双角色体系

WeKnora 有两套独立的角色：

**TenantRole**（`internal/types/tenant_member.go:18-33`）—— Tenant 内部 4 级：

```
Owner (40)       最高权限：删 Tenant、转交所有权、轮换 API Key
  │
Admin (30)       管理用户、集成、模型配置，不能删 Tenant / 改 Owner
  │
Contributor (20) 创建 KB / Agent，编辑自己创建的
  │
Viewer (10)      只读，跑被允许的 Agent
```

**OrgMemberRole**（`internal/types/organization.go:9-19`）—— Organization 内部 3 级：

```
Admin (3)   全权管理 Org 和共享资源
  │
Editor (2)  可编辑共享 KB 内容，不能改设置
  │
Viewer (1)  只读 + 检索
```

**正交性**：一个用户可以同时是 Tenant A 的 Owner、Tenant B 的 Contributor、Org X 的 Viewer。`TenantRole` 管"在我自己 Tenant 内能干什么"，`OrgMemberRole` 管"在共享空间里能干什么"。

### 5.2 3-D 上限规则

跨租户访问时，最终的 effective permission 是三个值的 **最小值**：

```
effective = min(
    share.Permission,        // 共享授予 Org 的角色
    org_member.Role,         // 调用方 Tenant 在 Org 中的角色
    tenant_role_cap,         // 调用方在自家 Tenant 的角色上限
)
```

代码实现见 `internal/application/service/kbshare.go:440-466`：

```go
func (s *kbShareService) CheckTenantKBPermission(...) {
    for _, share := range shares {
        tm, err := s.orgRepo.GetTenantMember(ctx, share.OrganizationID, callerTenantID)
        if err != nil { continue }

        effective := types.MinOrgRole(share.Permission, tm.Role)  // 1, 2 取最小
        effective = applyTenantRoleCap(effective, callerTenantRole) // 再被 Tenant 角色封顶

        if highest == "" || effective.HasPermission(highest) {
            highest = effective
        }
    }
    return highest, isShared, nil
}
```

**为什么需要 3-D**：
- 没有 `share.Permission` 上限 → 共享方无法控制授予力度
- 没有 `org_member.Role` 上限 → Org Admin 无法回收过度授权
- 没有 `tenant_role_cap` → 一个 Tenant Viewer（在自家 Tenant 是只读的）通过 Org 共享拿到 Editor 权限，绕过了自家 Tenant 的 RBAC

第三点是 #1303 Plan 3 引入 `applyTenantRoleCap` 的核心动机。

---

## 6. 跨租户 Key 解析链路

### 6.1 Model 可见性规则

`internal/application/repository/model.go:28-39`：

```go
func (r *modelRepository) GetByID(ctx context.Context, tenantID uint64, id string) (*types.Model, error) {
    var m types.Model
    if err := r.db.WithContext(ctx).Where("id = ?", id).Where(
        "(tenant_id = ? OR is_builtin = true)", tenantID,
    ).First(&m).Error; err != nil {
        // ...
    }
    return &m, nil
}
```

**铁律**：`tenant_id = ? OR is_builtin = true`。一个 Model 要么属于调用方的 Tenant，要么是全局 builtin（`tenant_id=10000`），否则查不到。

`List` 接口（model.go:42-63）也是同一个 WHERE 子句。

### 6.2 三条 effectiveTenantID 切换路径

跨租户访问时，调用方的 ctx 里的 `TenantID` 必须切换到源 Tenant，否则 Model 查不到、向量库读不到、对象存储读不到。WeKnora 有三条独立的切换路径：

**路径 1：直接 KB 操作（chunk/faq/tag/knowledge 路由）**

`internal/middleware/kb_access.go:286-293`：

```go
c.Set(KBAccessContextKey, access)
newCtx := context.WithValue(ctx, types.TenantIDContextKey, access.EffectiveTenantID)
c.Request = c.Request.WithContext(newCtx)
```

中间件 `RequireKBAccess` 解析 KB 归属，如果是共享 KB，把 ctx 里的 `TenantID` 重写为 `access.EffectiveTenantID`（即 KB 的源 Tenant）。下游 handler 读 `TenantIDFromContext` 自然命中源 Tenant。

**路径 2：通过共享 Agent 调用（QA 会话）**

`internal/handler/session/qa.go:303-345, 405-410`：

```go
// resolveAgent: 共享 Agent 返回时，effectiveTenantID = agent.TenantID
customAgent, effectiveTenantID := h.resolveAgent(ctx, c, request.AgentID)

// setupSSEStream: 用 effectiveTenantID 切换 baseCtx
if reqCtx.effectiveTenantID != 0 && h.tenantService != nil {
    if tenant, err := h.tenantService.GetTenantByID(reqCtx.ctx, reqCtx.effectiveTenantID); err == nil && tenant != nil {
        baseCtx = context.WithValue(...)
        logger.Infof(reqCtx.ctx, "Using effective tenant %d for shared agent (model/KB/MCP)", reqCtx.effectiveTenantID)
    }
}
```

**这条路径最关键**：Bob 通过共享 Agent 调用，baseCtx 切到 Alice 的 Tenant → Model 解析、KB 检索、MCP 调用全部用 Alice 的配置和 Key。

**路径 3：跨多 KB 的 Embedding Key 解析**

`internal/application/service/knowledgebase_search.go:44-77`：

```go
func (s *knowledgeBaseService) ResolveEmbeddingModelKeys(ctx context.Context, kbs []*types.KnowledgeBase) map[string]string {
    for ref := range uniqueRefs {
        // 用 KB 自己的 TenantID 切 ctx，而不是用调用方的
        tenantCtx := context.WithValue(ctx, types.TenantIDContextKey, ref.TenantID)
        model, err := s.modelService.GetModelByID(tenantCtx, ref.ModelID)
        // ...
    }
}
```

多 KB 混合检索时，每个 KB 用自家 Tenant 的 ctx 解析 Embedding Model，避免"调用方 Tenant 看不见源 Tenant 的 Model"导致检索失败。

### 6.3 端到端调用链：Bob 通过共享 Agent 访问 Alice 的 KB

设：
- Alice 在 Tenant A，建了 KB「营销」、Agent「营销助手」绑了 Model A（API Key 是 Alice 配的）
- Alice 把 Agent「营销助手」共享到 Org「Marketing」
- Bob 在 Tenant B，是 Marketing 的 Editor

Bob 提问"这个文档说了什么"：

```
1. 请求带 AgentID=营销助手，Bob ctx.TenantID=B
        │
        ▼
2. resolveAgent: 发现是共享 Agent
   effectiveTenantID = agent.TenantID = A
        │
        ▼
3. setupSSEStream: baseCtx.TenantID = A
   日志："Using effective tenant A for shared agent"
        │
        ▼
4. resolveChatModelID: 用 baseCtx 解析 Model
   → Model A（属于 Tenant A）的 Parameters.APIKey 出库
        │
        ▼
5. KB 检索: HybridSearch(ctx, kbID=营销)
   → ResolveEmbeddingModelKeys: 用 KB.TenantID=A 切 ctx
   → Embedding Model A（属于 Tenant A）的 Key 出库
        │
        ▼
6. LLM 调用: 用 Model A 的 API Key 发请求
   → 计费归属到 Alice 配置的 Key（Tenant A 的额度）
```

**结论**：消耗的是 Alice 配置的 Model A 的 API Key 额度。这就是"Key 跟着资源走，不跟着调用者走"的实现机制。

---

## 7. 共享机制详解

### 7.1 共享 KB（kb_shares）

**共享动作**：

```http
POST /api/v1/knowledge-bases/{kb_id}/share
{
  "organization_id": "org-xxx",
  "permission": "viewer"
}
```

后端动作（`internal/application/service/kbshare.go`）：

1. 校验调用方对 KB 的所有权（必须是 `kb.TenantID` 的成员且角色足够）
2. 校验调用方 Tenant 是 Org 的成员
3. 写入 `kb_shares` 行：`source_tenant_id = kb.TenantID`
4. 不修改 `knowledge_bases.tenant_id`

**取消共享**：删 `kb_shares` 行，KB 留在原 Tenant 不动。

### 7.2 共享 Agent（agent_shares）

**共享动作**：

```http
POST /api/v1/custom-agents/{agent_id}/share
{
  "organization_id": "org-xxx",
  "permission": "viewer"
}
```

后端动作类似 KB 共享。Agent 的绑定 KB 跟随 Agent 出现在 Org 中，但**不创建 `kb_shares` 行**，只通过 `agent.Config.KnowledgeBases` 字段引用。这些 KB 在 Org 列表中标记为"来自智能体 XXX"，只读。

代码实现见 `internal/types/organization.go:271-285`：

```go
type SourceFromAgentInfo struct {
    AgentID         string
    AgentName       string
    KBSelectionMode string  // "all" | "selected" | "none"
}
```

### 7.3 三步访问解析

任何 `/api/v1/.../kb_id/...` 路由（chunk 操作、FAQ 管理、tag 编辑、文档上传、KB 详情）都经过 `RequireKBAccess` 中间件，按顺序尝试三种授权路径：

`internal/middleware/kb_access.go:308-371`：

```go
func resolveKBAccessOnce(...) (*KBAccess, error) {
    // 1. 自己 Tenant 的 KB —— 直接放行
    if kb.TenantID == tenantID {
        return &KBAccess{
            KnowledgeBase:     kb,
            EffectiveTenantID: tenantID,
            Permission:        types.OrgRoleAdmin,
        }, nil
    }

    // 2. 通过 Org 共享进来 —— 应用 3-D 上限规则
    if kbShareService != nil {
        permission, isShared, _ := kbShareService.CheckTenantKBPermission(...)
        if isShared && permission.HasPermission(requiredPermission) {
            source, _ := kbShareService.GetKBSourceTenant(ctx, kbID)
            return &KBAccess{
                KnowledgeBase:     kb,
                EffectiveTenantID: source,
                Permission:        permission,
            }, nil
        }
    }

    // 3. 通过共享 Agent 携带（仅 viewer 级别）
    if requiredPermission == types.OrgRoleViewer && agentShareService != nil {
        if access := resolveSharedAgentAccess(...); access != nil {
            return access, nil
        }
    }

    return nil, errKBAccessForbidden
}
```

第 3 步的 `resolveSharedAgentAccess` 还区分两种子情况：

- **请求带 `?agent_id=X`**：精确验证该 Agent 的 `KBSelectionMode`（all/selected/none）。如果 KB 不在 Agent 的 KB 列表里，拒绝；不回退到"任意共享 Agent"。
- **请求没带 agent_id**：只要存在任意一个共享 Agent 能访问该 KB，就放行（"通过智能体可见"列表入口）。

---

## 8. 资产传承语义

### 8.1 Tenant 内成员被踢

**场景**：Tenant A 的 Owner 把 Contributor Alice 踢出。

| 资源 | 结果 |
|------|------|
| Alice 创建的 KB | ✅ **留在 Tenant A**。`knowledge_bases.creator_id` 仍是 Alice 的 user_id，但 KB 归属 `tenant_id=A` 不变 |
| Alice 配的 Model | ✅ **留在 Tenant A**。Model 归属 `tenant_id=A`，不是 Alice 个人 |
| Alice 的 TenantMember 行 | 软删除或 `status=suspended`，保留审计 |
| Alice 的 User 行 | 不变（她可能还属于其他 Tenant） |

**核心结论**：在 Tenant 内部，资源属于 Tenant 不属于个人。踢人不会"带走"任何资源。

### 8.2 Org 内租户被移除

**场景**：Org「Marketing」Admin 把 Tenant B 移除。

代码实现 `internal/application/repository/organization.go:133-145`：

```go
func (r *organizationRepository) RemoveTenantMember(...) error {
    result := r.db.WithContext(ctx).
        Where("organization_id = ? AND tenant_id = ?", orgID, tenantID).
        Delete(&types.OrganizationTenantMember{})
    // 注意：不级联删除 kb_shares！
}
```

| 资源 | 结果 |
|------|------|
| Tenant B 的 KB（共享到 Org 的） | ⚠️ **`kb_shares` 行可能仍存在**（见 [已知清理缺口](#84-已知清理缺口)） |
| Tenant B 用户对 Org 的访问 | ❌ 立即失效（TenantMember 删除 → `CheckTenantKBPermission` 跳过） |
| Tenant B 用户对共享 KB 的访问 | ❌ 间接失效（`CheckTenantKBPermission` 找不到 TenantMember → `isShared=false`） |
| OwnerTenantID | ✅ 不可删除（migration 000046 保证 Org 永不孤儿化） |

### 8.3 资产传承规则总结

| 操作 | 对资源的影响 |
|------|-------------|
| Tenant 内踢人 | 资源**留下**，归属 Tenant 不变 |
| Tenant 删除 | 资源**级联软删除**（`tenants.deleted_at` + 关联表） |
| Org 移除 Tenant | 资源不动，访问链路切断 |
| Org 删除 | 资源不动，`kb_shares` 跟随 Org 软删除（外键约束） |
| User 软删除 | 该 User 的 TenantMember 行级联，资源不动 |

### 8.4 已知清理缺口

`RemoveTenantMember` **不级联删除该 Tenant 共享进来的 `kb_shares` 行**。后果：

- Tenant B 被移出 Org 后，`kb_shares` 行 `(kb_id, org_id, source_tenant_id=B)` 仍在
- 任何后续 `CheckTenantKBPermission` 调用都会因为找不到 `organization_tenant_members` 行而返回 `isShared=false`，所以**安全上没漏洞**
- 但 `kb_shares` 表会积累"孤儿"行，长期看需要清理任务

**建议（不在本 PR 范围）**：在 `RemoveTenantMember` 中加一步：

```go
// 伪代码
db.Where("organization_id = ? AND source_tenant_id = ?", orgID, tenantID).
    Delete(&types.KnowledgeBaseShare{})
db.Where("organization_id = ? AND source_tenant_id = ?", orgID, tenantID).
    Delete(&types.AgentShare{})
```

---

## 9. 邀请与加入流程

### 9.1 Tenant 邀请（加入工作空间）

**入口**：Tenant Owner/Admin 在"工作空间设置 → 成员管理"页面发起。

**路由**：`internal/router/router.go:599-601`

```go
tenantByID.POST("/invitations", g.Owner(), invitationHandler.CreateInvitation)
me.GET("/invitations", invitationHandler.ListMyInvitations)
me.POST("/invitations/:inv_id/accept", invitationHandler.AcceptMyInvitation)
```

**接受入口**：前端铃铛 `frontend/src/components/GlobalInvitationBell.vue`：

```vue
<template v-if="pendingInvitationCount > 0">
  <t-badge :count="pendingInvitationCount" ...>
    <!-- 铃铛图标 -->
  </t-badge>
</template>
```

**轮询机制**：`App.vue:162` 每 2 分钟调用 `ListMyInvitations`，`pendingInvitationCount > 0` 时显示铃铛。

**接受动作**：调用 `POST /me/invitations/:inv_id/accept` → 后端创建 `tenant_members` 行（`status=active`）。

### 9.2 Organization 邀请（加入共享空间）

**两种加入方式**：

**方式 A：邀请码加入**

```http
POST /api/v1/organizations/join
{ "invite_code": "..." }
```

- Org Admin 生成邀请码（`InviteCodeValidityDays`：0/1/7/30 天）
- 任意用户拿到邀请码即可加入（如果 `RequireApproval=false`）
- 如果 `RequireApproval=true`，提交 join_request 等审批

**方式 B：搜索发现加入**

```http
POST /api/v1/organizations/join-by-id
{ "organization_id": "org-xxx" }
```

- 仅当 `Organization.Searchable=true` 时可用
- 用于"公司全员 Org"这种公开空间

**加入的单位**：当前用户的 Home Tenant 整个加入 Org（创建 `organization_tenant_members` 行）。如果用户后续切换 Home Tenant，新 Tenant 不会自动加入。

### 9.3 OIDC SSO 自动建租户

`internal/router/router.go:706-708`：

```go
r.GET("/auth/oidc/config", handler.GetOIDCConfig)
r.GET("/auth/oidc/url", handler.GetOIDCAuthorizationURL)
r.GET("/auth/oidc/callback", handler.OIDCRedirectCallback)
```

**回调流程**：

1. OIDC Provider 回调到 `/auth/oidc/callback?code=...`
2. 后端用 code 换 id_token / userinfo
3. 用 email 查 User：
   - 存在 → 直接登录，返回 Home Tenant 信息
   - 不存在 → **自动建 User + 自动建 Home Tenant**（名字默认 `email 的 @ 之前部分` 或 OIDC 提供的 name）
4. 返回 token，前端跳到首页

**关键**：每个 OIDC 用户至少有一个 Home Tenant，不会出现"登录后没空间可用"的状态。

---

## 10. 关键设计权衡

### 权衡 1：Tenant 必须存在 vs 用户自助建 Tenant

**决策**：保留 Tenant 层，但允许任意已登录用户自助建 Tenant。

**理由**：
- 公司内部场景：人事、IT 部门集中建 Tenant，分配给员工
- 但也要允许"项目级 Tenant"（短期项目隔离）、"部门实验 Tenant"（试点用）
- 完全禁止自助建 → 增加运维负担；完全自由 → 治理混乱

**实现**：`POST /api/v1/tenants` 任意已登录用户可调用，`frontend/src/components/CreateTenantDialog.vue` 注释明确说明这一点。

### 权衡 2：Org 成员单位是 User 还是 Tenant

**决策**：按 Tenant（Plan 3 #1303 之后）。

**理由**：
- 共享语义是"我把这个 KB 共享给某个团队"，不是"共享给某个个人"
- 个人调岗、离职时，团队接手是 Tenant 级动作，不是 User 级
- 权限计算简单：`(org, tenant)` 二元组，不需要追溯 User 的多重 Tenant 归属

**代价**：跨 Tenant 协作的颗粒度是 Tenant 不是个人。一个 Tenant 内的所有人共享同一个 Org 角色。如果需要"细到个人"，得在 Tenant 内部用 TenantRole 控制。

### 权衡 3：共享 Agent 携带的 KB 不创建 kb_shares 行

**决策**：Agent 共享时，绑定的 KB 通过 Agent 的 config 引用，不创建独立 `kb_shares`。

**理由**：
- 避免数据冗余
- 取消 Agent 共享时不需要级联清理 KB 共享
- 列表展示通过 `SourceFromAgentInfo` 标记"来自智能体 XXX"

**代价**：在 `kb_access` 中间件中要专门处理 `?agent_id=X` 路径（步骤 3），逻辑比纯 KB 共享复杂。

### 权衡 4：Builtin Model 的全局可见性

**决策**：Model 表加 `is_builtin` 字段，`is_builtin=true` 的行所有 Tenant 可见。

**理由**：
- 系统级模型（如默认 embedding、rerank）需要给所有 Tenant 用
- 不需要每个 Tenant 都配一份相同的 Model 行

**代价**：
- Builtin Model 的 API Key 由系统管理员维护，Tenant 用户改不了
- Tenant 用户能消耗 Builtin Model 的额度但没有节制手段 → 需要在系统级加 rate limit

### 权衡 5：3-D 上限规则 vs 简单的 share.Permission

**决策**：effective permission = min(share.Permission, org_member.Role, tenant_role_cap)。

**理由**：
- 防止 Tenant Viewer 通过 Org 共享绕过自家 Tenant 的只读限制
- 防止 Org Admin 过度授权（Org Admin 给的 Editor 不能超过调用方 Tenant 角色）

**代价**：权限计算稍复杂，但 `MinOrgRole` / `applyTenantRoleCap` 封装后调用方代码仍清晰。

---

## 11. 关键文件索引

### 数据结构（types）

| 文件 | 内容 |
|------|------|
| `internal/types/tenant.go` | Tenant 结构、StorageEngineConfig、CredentialsConfig |
| `internal/types/tenant_member.go` | TenantMember、TenantRole 4 级体系 |
| `internal/types/organization.go` | Organization、OrganizationTenantMember、KnowledgeBaseShare、AgentShare、OrgMemberRole 3 级体系 |
| `internal/types/model.go` | Model 结构、IsBuiltin、DefaultBuiltinModelTenantID=10000 |
| `internal/types/knowledgebase.go` | KnowledgeBase 结构、TenantID、CreatorID、EmbeddingModelID |

### 中间件

| 文件 | 内容 |
|------|------|
| `internal/middleware/kb_access.go` | RequireKBAccess 守卫、三步访问解析、EffectiveTenantID 切换（直接 KB 路径） |
| `internal/middleware/auth.go` | Tenant 上下文初始化、TenantMember 校验 |
| `internal/middleware/role.go` | RequireRole、RequireOwner |

### 仓储层

| 文件 | 内容 |
|------|------|
| `internal/application/repository/model.go` | Model 可见性规则 `tenant_id = ? OR is_builtin = true` |
| `internal/application/repository/organization.go` | Org / OTM / kb_shares / agent_shares 仓储；RemoveTenantMember（不级联） |
| `internal/application/repository/tenant.go` | Tenant 仓储、API Key 加解密 |

### 服务层

| 文件 | 内容 |
|------|------|
| `internal/application/service/kbshare.go` | CheckTenantKBPermission、3-D 上限规则、GetKBSourceTenant |
| `internal/application/service/agentshare.go` | Agent 共享、TenantCanAccessKBViaSomeSharedAgent |
| `internal/application/service/knowledgebase_search.go` | ResolveEmbeddingModelKeys（多 KB 跨租户 Key 解析） |
| `internal/application/service/organization.go` | Org 创建/邀请/加入/审批 |
| `internal/application/service/tenant.go` | Tenant 创建、自助建、OIDC 自动建 |
| `internal/application/service/session_qa_helpers.go` | resolveChatModelID（QA 会话 Model 解析） |

### Handler 层

| 文件 | 内容 |
|------|------|
| `internal/handler/session/qa.go` | resolveAgent、setupSSEStream（共享 Agent 的 EffectiveTenantID 切换，关键路径 2） |
| `internal/handler/organization.go` | Org CRUD、加入、邀请、审批 |
| `internal/handler/invitation.go` | Tenant 邀请 |
| `internal/handler/oidc.go` | OIDC SSO 回调 |
| `internal/handler/tenant.go` | Tenant CRUD、自助建 |

### 路由

| 文件 | 内容 |
|------|------|
| `internal/router/router.go` | 所有路由聚合点；706-708 OIDC 路由；599-601 邀请路由 |

### 前端

| 文件 | 内容 |
|------|------|
| `frontend/src/components/GlobalInvitationBell.vue` | Tenant 邀请铃铛、2 分钟轮询 |
| `frontend/src/components/CreateTenantDialog.vue` | 自助建 Tenant 弹窗 |
| `frontend/src/views/organization/*` | 共享空间管理界面 |
| `frontend/App.vue` | 铃铛轮询定时器（line 162） |

### 迁移

| 文件 | 内容 |
|------|------|
| `migrations/versioned/000046_*.up.sql` | Organization.OwnerTenantID 不可改不可删约束 |
| `migrations/versioned/000050_*.up.sql` | user_kb_pins（pin 解耦到用户级） |
| `migrations/versioned/000000_init.up.sql` | tenants / organizations / kb_shares 初始结构 |

### 相关文档

| 文件 | 内容 |
|------|------|
| `CONTEXT.md` | 项目领域术语总览（含 Multi-tenant layer 章节） |
| `docs/wiki-architecture.md` | Wiki 子系统架构（独立的另一套检索路径） |
| `docs/wiki/安全认证/共享空间说明.md` | 共享空间产品说明（用户视角） |
| `docs/wiki/核心功能/内置模型管理.md` | Builtin Model 说明 |
| `docs/wiki/安全认证/OIDC认证调用流程.md` | OIDC 详细流程 |

---

## 附录：术语速查

| 中文 | 英文 | 一句话定义 |
|------|------|-----------|
| 工作空间 | Tenant | 资源归属边界（账户） |
| 共享空间 | Organization | 跨租户协作载体（通道） |
| 主工作空间 | Home Tenant | 用户登录后默认所属的 Tenant |
| 共享指针 | kb_shares / agent_shares | 把资源"发布"到 Org 的记录，不改变归属 |
| 源租户 | SourceTenantID | 共享资源的原始归属 Tenant |
| 生效租户 | EffectiveTenantID | 跨租户访问时切换到的目标 Tenant |
| 创建者 | CreatorID | KB 的原始创建人，仅用于 RBAC，不影响归属 |
| 内置模型 | Builtin Model | `is_builtin=true`，所有 Tenant 可见的全局 Model |
| 3-D 上限 | 3-D Cap | effective = min(share, org_role, tenant_role_cap) |

---

_本文档基于 2026-07-05 时的代码状态整理。后续如有架构调整（特别是 #1303 后续 Plan），请同步更新本文档与 `CONTEXT.md` 的 Multi-tenant layer 章节。_
