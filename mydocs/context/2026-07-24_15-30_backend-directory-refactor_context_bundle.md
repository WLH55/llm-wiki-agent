# Context Bundle: backend 目录结构重构

## 1. Source Index

- 用户需求：检查 `backend/` 目录结构是否合理，并调整为更清晰的结构。
- 用户已确认的偏好：模块内部区分 `api` / `service` / `utils`，避免职责混杂。
- 用户明确限制：不使用 TDD，不使用 subagent-driven-development。
- 仓库规则：`AGENT.md`、`sdd-riper-one/SKILL.md`。
- 代码事实：`backend/app/**`、`backend/tests/**`、`backend/pyproject.toml`。
- 前置 Spec：`mydocs/specs/2026-07-24_14-50_parsers-module-structure-refactor.md`。
- 项目索引：`mydocs/codemap/2026-07-24_15-30_backend项目总图.md`。

## 2. Requirement Snapshot

- **Goal**: 将后端从“业务模块 + 横向分层混用”统一为“业务模块优先 + 少量共享基础设施”。
- **Behavior constraint**: 不改 HTTP API、数据库 schema、parser 行为、搜索算法、认证逻辑和 worker 任务入口。
- **Structure preference**: API DTO 与路由归属功能模块的 `api` 包；业务逻辑归 `service` 包；第三方调用与业务 service 分离。
- **Shared boundary decision**: 顶层共享 HTTP/FastAPI 基础使用 `app/web` 命名，与业务模块内的 `api` 区分；框架无关应用异常归 `app/core`。
- **Preservation constraint**: 保留当前未提交的 parser 重构和其他用户改动，不执行破坏性 Git 操作。

## 3. Key Facts

- `parsers` 已经形成清晰的模块内部分层，可作为其他功能的组织参考。
- `auth` 是半模块化状态：路由在 `auth`，schema 却在顶层 `schemas`。
- KB 和 Search 完全按 `routers/schemas/services` 横向分散。
- `services` 混合了业务逻辑（KB/Search）与外部系统适配（Embedding/MinIO）。
- `config` 包含 FastAPI DI、异常响应和 API schema，并反向依赖 auth/models/database，不是纯配置包。
- `deps.py` 只是 `config.dependencies` 的 re-export，产生两个同等入口。
- 集中 `models` 和独立 `workers` 在当前规模下有合理性，无需为追求形式一致而拆散。

## 4. Constraints

- 本任务是结构重构，必须保持外部行为。
- 不增加旧内部 import path 兼容层，仓库内消费方同步迁移。
- 不移动 `workers.queue.run_parse_document`，避免影响已入队 RQ job 的可导入路径。
- 不拆分 SQLAlchemy models，不新增 Alembic migration。
- 执行前必须收到精确授权 `Plan Approved`。

## 5. Open Questions

- 无业务需求歧义。
- 待用户确认推荐的模块化单体方案并授权执行。

## 6. Next Actions

1. 审阅 `mydocs/specs/2026-07-24_15-30_backend-directory-structure-refactor.md` 中的目标结构与文件迁移表。
2. 用户回复精确字样 `Plan Approved` 后进入 Execute。
3. 按模块分批迁移，每批执行 import 扫描、编译和相关回归。
