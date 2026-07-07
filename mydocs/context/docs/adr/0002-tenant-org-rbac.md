# Tenant + Organization 两层 RBAC 模型

每个用户拥有一个**自家 tenant**（自创 KB 都挂在这里），跨用户共享通过 **organization**（共享容器，admin 邀请成员）+ **kb_share**（KB 显式共享给某个 org）实现。权限合并走 **fall-through 三步短路**：自有 KB 全权；共享 KB = `min(share_perm, my_org_role)`，且 `my_tenant_role == Viewer && effective >= Editor` 时硬封顶到 Viewer；agent 间接共享 → Viewer；否则 403。

共享的粒度是 `(kb_id, org_id, permission)`，**不带 user_id**——这是有意的设计选择：组织成员变动（升职、调岗、离职）时只改 `org_members` 一张表，不需要逐条重写 KB 共享记录。

## Context

PRD v4.2 原本的"workspace + kb_grant + membership 三档 min()"模型存在两个根本缺陷：

1. **KB 所有者被自家角色压制（逻辑 bug）**：`min(L1 workspace默认, L2 kb_grant, L3 membership)` 让 KB owner 在自家 KB 上也会被 L3 角色压成 reader。参考项目 UI 截图佐证：wlh 自创的 faq 和 ss 两个 KB，在「空间视角」下显示"我的实际权限: 只读"——这是 min 合并的副作用，但**对所有者而言是反直觉的**。我们的产品语义是"自有即全权"，不应被自家设的角色压制。
2. **kb_grants.user_id 粒度无法承载组织级共享**：原 PRD 的 `kb_grants` 表带 user_id 字段，无法表达"org admin 换人后权限自动延续""新成员加入 org 自动获得基础权限"。每次人员变动都要逐条改 user 共享记录，运维噩梦。

## Decision

采纳**两层 RBAC 模型**：

```
┌──────────────────────────────────────────────────────────────┐
│  Tenant（自家）          Organization（共享容器）              │
│  ──────────────           ──────────────                     │
│  每个 user 默认有           admin 创建 + 邀请成员              │
│  一个自家 tenant            挂载来自不同 tenant 的 KB           │
│                                                           │
│  TenantRole:               OrgMemberRole:                   │
│    owner / admin /           admin / editor / viewer         │
│    contributor / viewer                                     │
│                                                           │
│  KB 创建在 caller 的         KB 通过 kb_share 共享进来         │
│  当前 tenant 上下文                                         │
└──────────────────────────────────────────────────────────────┘

              KB ←─ kb_share(kb_id, org_id, permission) ─→ Org
                              无 user_id 字段
```

### 合并算法（fall-through 三步短路）

```
resolveKBAccessOnce(caller, kb):
  # 第 1 步：自有 KB → Admin（无视任何角色）
  if caller.tenantID == kb.tenantID:
      return Admin

  # 第 2 步：通过 kb_share 共享到 caller 所在的 org
  share = kb_shares.where(kb_id=kb.id, org_id in caller.org_ids).first()
  if share:
      effective = min(share.permission, my_org_role_in(share.org_id))
      effective = applyTenantRoleCap(effective, my_tenant_role)
      return effective

  # 第 3 步：通过 agent 共享间接可见
  if caller can see kb via agent_share:
      return Viewer

  # 兜底
  return 403 Forbidden


applyTenantRoleCap(effective, my_tenant_role):
  # 只封一种情况：租户级 Viewer 且 effective >= Editor → 砍到 Viewer
  if my_tenant_role == Viewer and effective >= Editor:
      return Viewer
  return effective
```

**关键点**：
- `applyTenantRoleCap` **只封一种情况**——my_tenant_role == Viewer 且 effective >= Editor 时砍到 Viewer。其他情况一律不封。这是有意的最小化封顶，避免重蹈 PRD 三档 min() 的覆辙。
- 共享是 **org-level 不是 user-level**：`(kb_id, org_id, permission)` 三元组，无 user_id。
- **自有即全权**：第 1 步短路，owner/admin 在自家 tenant 内的 KB 永远是 Admin，无视任何角色配置。

### 「空间视角下显示只读」的语义解释

参考项目 UI 截图里 wlh 自创 KB 在「空间视角」下显示只读，**不是 bug**，是**有意的可审计设计**：
- 在「我的 KB」视图（tenant 视角）：wlh 是 owner，看到 Admin。
- 在「空间 KB 列表」视图（org 视角）：UI 显式标注"空间权限: 只读 / 我的实际权限: 只读"——这是 wlh **作为这个 org 的成员**所获得的共享权限，与"我是 KB owner"无关。
- 两个视角分离是有意义的：admin 调整 org 的共享上限时，UI 能立刻反映"这个 org 现在对这个 KB 的访问权限是 X"，便于审计。

我们的产品**保留**这种双视角分离设计，但在「我的 KB」视图（tenant 视角）下，所有自创 KB 都显示 Admin（owner 视角）。

## Considered Options

- **PRD v4.2 单层 workspace + 三档 min()（L1 workspace默认 / L2 kb_grant / L3 membership）**：rejected。`min()` 让 KB 所有者被自家设的 viewer 角色压制，逻辑 bug。`kb_grants.user_id` 粒度也无法承载组织级共享。
- **纯 user-level 共享**（kb_grants 保留 user_id）：rejected。org 成员变动（升职、调岗、离职）时需要逐条改 user 共享记录，无法批量收敛；org admin 换人后历史共享记录失去意义。我们选择 org-level 共享，人员变动只改 `org_members` 一张表。
- **每个 KB 一张独立 ACL 表**：rejected。N×M 复杂度爆炸，且失去"组织"这一层语义抽象（无法表达"研发组所有人都能读这两个 KB"）。
- **Postgres RLS（Row-Level Security）**：rejected for default。应用层 RBAC 已够自注册 + 邀请制场景。RLS 是企业级兜底，留作未来企业版升级路径（参 [CONTEXT.md 强制工作空间隔离] 条目的注释）。

## Consequences

- **schema 改动**：
  - 所有业务表加 `tenant_id` 列：`knowledge_bases` / `pages` / `content_chunks` / `sources` / `wiki_pages` / `wiki_folders` 等。
  - 新增 `organizations` 表（id, name, created_by, created_at）。
  - 新增 `org_members` 表（org_id, user_id, role: admin/editor/viewer, joined_at）。
  - `kb_shares` 表（kb_id, org_id, permission: viewer/editor/admin, shared_by, shared_at）——**无 user_id**。
- **应用层校验**：每次跨 KB 操作（读 chunk / 写 wiki / 检索）都必须先调 `resolveKBAccessOnce(caller, kb)` 走 fall-through 三步短路，结果作为唯一权限源。
- **UI 上下文切换**：用户登录后必须选择"当前 workspace context"（自家 tenant / 某 organization），所有 API 调用都带 `X-Workspace-Context` header。无 context 的查询一律 400。
- **测试矩阵**：DB 集成测试覆盖 fall-through 四分支（自有 / 直接共享 / agent 间接 / 未共享）+ applyTenantRoleCap 五种 (effective, tenant_role) 组合。
- **失去的灵活性**：无法对单个用户单独 grant KB（必须先创建 organization，把用户加进去，再共享 KB 给 org）。这是有意的——避免 user-level 共享记录爆炸。
- **与现有术语的兼容**：原 PRD v4.2 的「workspace」概念被拆分为 tenant（自家）+ organization（共享）。PRD 的 user stories 19-22、Implementation Decisions「三档 RBAC」章节需要按本 ADR 重写。

## 参考实现

参考项目（Go + Vue）已实现此模式：

- `internal/auth/kb_access.go:308` — `resolveKBAccessOnce` fall-through 三步短路入口
- `internal/auth/kbshare.go:440` — `effective = min(share.Permission, myOrgRole)` 公式
- `internal/auth/kbshare.go:65` — `applyTenantRoleCap` 硬封顶（只封 viewer×editor+ 一种情况）
- `web/src/utils/kbListMerge.ts:70` — 列表层合并（KB list 显示空间权限 vs 我的实际权限）
- `web/src/components/KBShareSettings.vue:269` — 共享设置 UI

llm_wiki3.0 用 FastAPI + SQLAlchemy，应用层 `resolve_kb_access_once` 函数照搬逻辑；schema migration 直接照搬 organizations / org_members / kb_shares 三张表的 DDL，业务表加 `tenant_id` 列即可。
