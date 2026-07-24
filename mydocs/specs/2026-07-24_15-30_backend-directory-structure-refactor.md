# SDD Spec: backend 目录结构重构

## RIPER 状态

- **phase**: REVIEW
- **status**: LOCKED
- **approval status**: `Plan Approved` (2026-07-24)
- **execution mode**: Batch Override（用户要求一次性完成后汇报）；不使用 TDD，不使用 subagent-driven-development
- **spec path**: `mydocs/specs/2026-07-24_15-30_backend-directory-structure-refactor.md`
- **active project**: `backend`
- **active workdir**: `backend/`
- **change scope**: local

## 0. Open Questions

- [x] 用户已批准本 Spec 的推荐方案（`Plan Approved`，2026-07-24）。

## 1. Requirements (Context)

- **Goal**: 将 `backend/app` 调整为职责清晰、依赖方向可见的模块化单体结构，降低新增和修改业务功能时的跨目录认知成本。
- **In-Scope**:
  - 将 Auth、Knowledge Base、Search 统一为业务模块，模块内部分离 `api` 与 `service`。
  - 保留并复用已完成的 `parsers/api|service|core|implementations|utils` 结构。
  - 将全局 HTTP 响应模型、FastAPI 异常处理和通用 DB 依赖收拢到 `app/web`。
  - 将框架无关的应用级异常收拢到 `app/core/exceptions.py`。
  - 将 Current User 认证依赖放到 `app/auth/api`，防止共享 Web 层反向依赖 Auth。
  - 将 Embedding 和 MinIO 客户端收拢到 `app/integrations`。
  - 更新仓库内 import、测试、应用装配与相关 Spec 的路径描述。
- **Out-of-Scope**:
  - 不修改 HTTP 路径、HTTP 方法、请求字段、响应结构或 OpenAPI 契约。
  - 不修改数据库表、SQL、Alembic migration 或 ORM 关系。
  - 不改动 parser 算法、搜索算法、分块、Embedding、MinIO、认证和 RQ 行为。
  - 不拆分 `app/models`，不移动 `workers.queue.run_parse_document`。
  - 不新增旧内部 import path 的兼容 shim。
  - 不处理现有编码异常注释、命名细节或其他非结构性技术债。

### Acceptance Criteria

1. `backend/app` 不再存在顶层 `routers/`、`schemas/`、`services/` 业务大杂烩包。
2. Auth、Knowledge Base、Search、Parsers 的 API 和 service 均由各自模块所有。
3. `app/config` 只保留 settings 与 logging 配置，不再依赖 auth、models 或 database。
4. `app/web` 只保留跨模块 HTTP/FastAPI 基础；`app/web` 不依赖任何业务模块。
5. `app/core/exceptions.py` 保存框架无关的应用级异常，parser 内部异常仍由 `app/parsers/errors.py` 所有。
6. Embedding 和 Object Storage 的代码位于 `app/integrations`，业务 service 不与第三方适配混放。
7. 旧代码路径扫描结果为 0，全部 Python 文件可编译，Ruff `E/F/I` 通过。
8. 现有可运行测试通过，OpenAPI 路径及关键请求/响应 schema 与重构前一致。
9. 不覆盖、回退或清理用户现有未提交改动。

## 1.1 Context Sources

- Requirement Source: 当前对话中的后端目录结构调整需求。
- Design Refs: `mydocs/specs/2026-07-24_14-50_parsers-module-structure-refactor.md`。
- Repository Rules: `AGENT.md`、`C:/Users/Lathan/.agents/skills/sdd-riper-one/SKILL.md`。
- Extra Context: 用户明确不使用 TDD 和 subagent-driven-development。

## 1.5 Codemap Used (Project Index)

- Codemap Mode: `project`
- Codemap File: `mydocs/codemap/2026-07-24_15-30_backend项目总图.md`
- Key Index:
  - Entry Point: `backend/app/main.py`
  - Mixed horizontal layers: `backend/app/routers`、`backend/app/schemas`、`backend/app/services`
  - Feature modules: `backend/app/auth`、`backend/app/parsers`
  - Shared persistence/runtime: `backend/app/models`、`backend/app/workers`、`backend/app/database.py`
  - External systems: PostgreSQL、Redis/RQ、MinIO、OpenAI-compatible Embedding API

## 1.6 Context Bundle Snapshot (Lite)

- Bundle Level: `Lite`
- Bundle File: `mydocs/context/2026-07-24_15-30_backend-directory-refactor_context_bundle.md`
- Key Facts: 当前同时存在业务模块优先和横向分层两种组织方式；`config` 与 `services` 均有职责混杂。
- Open Questions: 无业务歧义，仅等待执行授权。

## 2. Research Findings

### 事实与问题

1. `parsers` 已按功能模块内分层，但 KB/Search 仍按 `routers/schemas/services` 横向分层，顶层语义不一致。
2. `auth/routes.py` 与 `schemas/auth.py` 分属两个顶层包，且登录路由直接承载用户查询和鉴权业务。
3. `config.dependencies` 导入 auth、database 和 models，使“配置”层反向依赖业务/持久化层。
4. `config.schemas` 和 `config.exceptions` 是 HTTP 边界概念，不是配置。
5. `services` 混合了 KB/Search 业务逻辑与 MinIO/Embedding 外部适配，无法从目录名判断依赖性质。
6. `models` 包含跨领域 SQLAlchemy 关系，且 Alembic 统一 import；当前将其拆到业务模块会放大风险，收益不足。
7. `workers.parse_document` 是跨 parser、storage、embedding、database 的应用编排，不等同于 parser 实现；保留在 workers 更符合运行边界。

### 风险与约束

- 当前 parser 重构处于未提交状态，本任务必须在现有工作区基础上继续，不得还原。
- 文件移动会改变内部 import path，但不应影响 HTTP/API 契约。
- `__init__.py` 若急切导出 router，可能在单纯 import schema 时提前初始化 DB；模块入口需保持轻量。

## 2.1 Next Actions

1. 用户审阅目标结构、文件迁移和 Out-of-Scope。
2. 用户回复精确字样 `Plan Approved`。
3. 按 `core/web/config -> auth -> knowledge_bases -> search -> integrations -> consumers/tests/docs` 顺序执行。

## 3. Innovate (Options & Decision)

### Option A: 业务模块优先 + 共享 Web/Core/Integrations（推荐）

- **Structure**: Auth、Knowledge Base、Search、Parsers 各自拥有 API 和 service；全局 HTTP 基础放 `app/web`；框架无关应用异常放 `app/core`；外部系统适配放 `app/integrations`。
- **Pros**: 修改一个业务时文件就近；模块所有权清晰；与已批准的 parser 结构方向一致；不需要拆 ORM。
- **Cons**: 会产生若干小包；所有仓库内 import 需要同步迁移。

### Option B: 继续纯横向分层

- **Structure**: 继续使用顶层 `routers/schemas/services`，将 parser 也拆回横向层。
- **Pros**: 初学者能按文件类型快速定位。
- **Cons**: 业务增长后顶层目录持续膨胀；破坏已完成的 parser 模块化；功能修改跨多目录。

### Option C: 完整 DDD/洁净架构拆分

- **Structure**: 每个领域拥有 domain/application/infrastructure/repository/model，通过端口适配器解耦。
- **Pros**: 边界最强，适合大型团队与复杂领域。
- **Cons**: 当前 MVP 规模下会引入大量抽象和迁移，与“保持行为的目录整理”不匹配。

### Decision

- **Selected**: Option A（待用户批准）
- **Why**: 它解决当前真实的职责混合，又不引入 repository/domain entity 等过早抽象；同时尊重用户已确认的 parser 模块组织偏好。

## 4. Plan (Contract)

### 4.1 Target Structure

```text
backend/app/
├── main.py
├── database.py
├── config/
│   ├── settings.py
│   └── logging.py
├── core/
│   └── exceptions.py         # 框架无关的应用异常
├── web/
│   ├── dependencies.py       # get_db / DbDep
│   ├── exception_handlers.py # FastAPI 异常转换与注册
│   └── schemas.py            # ApiResponse / PageResponse / ResponseCode
├── auth/
│   ├── api/
│   │   ├── dependencies.py   # CurrentUserDep
│   │   ├── routes.py
│   │   └── schemas.py
│   ├── service/
│   │   ├── auth.py           # 登录鉴权业务
│   │   └── bootstrap.py
│   └── security/
│       ├── jwt.py
│       └── password.py
├── knowledge_bases/
│   ├── api/
│   │   ├── routes.py
│   │   └── schemas.py
│   └── service/
│       └── knowledge_base.py
├── search/
│   ├── api/
│   │   ├── routes.py
│   │   └── schemas.py
│   └── service/
│       └── search.py
├── parsers/                   # 保留现有内部结构
├── integrations/
│   ├── embedding.py
│   └── object_storage.py
├── models/                    # 保留集中 ORM
├── workers/                   # 保留 RQ 入口/编排
└── plugins/
```

### 4.2 File Changes

#### Shared Core, Web and Config

- `backend/app/config/schemas.py` -> `backend/app/web/schemas.py`：全局 HTTP 响应契约。
- `backend/app/config/exceptions.py` -> 拆分为 `backend/app/core/exceptions.py` 与 `backend/app/web/exception_handlers.py`：前者保存框架无关异常，后者负责 FastAPI 响应转换。
- `backend/app/config/dependencies.py` -> 拆分为 `backend/app/web/dependencies.py` 与 `backend/app/auth/api/dependencies.py`。
- `backend/app/deps.py`：删除重复 re-export，消费方改用明确所有者路径。
- `backend/app/config/logger_config.py` -> `backend/app/config/logging.py`。
- `backend/app/config/__init__.py`：只导出 `settings` 和 `setup_logging`。
- `backend/app/core/__init__.py`、`backend/app/web/__init__.py`：新建无副作用包入口。

#### Auth Module

- `backend/app/auth/routes.py` -> `backend/app/auth/api/routes.py`。
- `backend/app/schemas/auth.py` -> `backend/app/auth/api/schemas.py`。
- `backend/app/auth/bootstrap.py` -> `backend/app/auth/service/bootstrap.py`。
- `backend/app/auth/jwt_handler.py` -> `backend/app/auth/security/jwt.py`。
- `backend/app/auth/password.py` -> `backend/app/auth/security/password.py`。
- `backend/app/auth/service/auth.py`：新建，从 route 提取用户查询、密码校验、账号状态校验与 token 生成。
- 新建 `api/service/security` 各级 `__init__.py`，保持无急切业务导入。

#### Knowledge Base Module

- `backend/app/routers/kb.py` -> `backend/app/knowledge_bases/api/routes.py`。
- `backend/app/schemas/kb.py` -> `backend/app/knowledge_bases/api/schemas.py`。
- `backend/app/services/kb_service.py` -> `backend/app/knowledge_bases/service/knowledge_base.py`。
- 新建 `backend/app/knowledge_bases/__init__.py`、`api/__init__.py`、`service/__init__.py`，均不触发 DB 初始化。

#### Search Module

- `backend/app/routers/search.py` -> `backend/app/search/api/routes.py`。
- `backend/app/schemas/search.py` -> `backend/app/search/api/schemas.py`。
- `backend/app/services/search_service.py` -> `backend/app/search/service/search.py`。
- 新建 `backend/app/search/__init__.py`、`api/__init__.py`、`service/__init__.py`，均不触发 DB 初始化。

#### Integrations

- `backend/app/services/embedding_service.py` -> `backend/app/integrations/embedding.py`。
- `backend/app/services/minio_service.py` -> `backend/app/integrations/object_storage.py`。
- 新建 `backend/app/integrations/__init__.py`，不急切创建第三方 client。

#### Consumers, Tests and Docs

- `backend/app/main.py`：更新 exception handler、bootstrap 和路由 import。
- `backend/app/parsers/api/document.py`：改用 shared Web DB dependency、Auth dependency 和 shared Web schema。
- `backend/app/parsers/service/document.py`：改用 Core exception、Knowledge Base service 和 Object Storage adapter。
- `backend/app/parsers/service/asset.py`：改用 Object Storage adapter。
- `backend/app/workers/parse_document.py`：改用 Embedding/Object Storage adapter，不改 worker 入口。
- `backend/tests/conftest.py`、`backend/tests/test_auth.py`、`backend/tests/test_parser_hardening_service.py` 及扫描命中的测试：更新 import/monkeypatch 路径。
- `mydocs/specs/2026-07-24_14-50_parsers-module-structure-refactor.md`：同步 shared Web/Core 和 integration 新路径，不改变该 Spec 的完成结论。
- 完成迁移后删除已空的 `backend/app/routers`、`backend/app/schemas`、`backend/app/services`。

### 4.3 Signatures

- `async def get_db() -> AsyncIterator[AsyncSession]`：行为不变，新所有者为 `app.web.dependencies`。
- `DbDep = Annotated[AsyncSession, Depends(get_db)]`：新所有者为 `app.web.dependencies`。
- `async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: Annotated[AsyncSession, Depends(get_db)]) -> User`：行为不变，新所有者为 `app.auth.api.dependencies`。
- `CurrentUserDep = Annotated[User, Depends(get_current_user)]`：新所有者为 `app.auth.api.dependencies`。
- `async def authenticate_user(db: AsyncSession, email: str, password: str) -> User`：新建于 `app.auth.service.auth`，失败时保持现有 `BusinessValidationException` 语义。
- `async def login(payload: LoginRequest, db: DbDep) -> ApiResponse[TokenResponse]`：路由签名与响应不变，内部委托 Auth service。
- KB/Search/Parser 的已有公开函数签名均保持不变，仅改变模块路径。
- `run_parse_document(doc_id: str) -> None` 与 `enqueue_parse_document(doc_id: str) -> None` 的路径和签名保持不变。

### 4.4 Dependency Rules

```text
main -> feature.api
feature.api.routes -> app.web + auth.api.dependencies + feature.service
feature.service -> module-local leaf schemas + models + integrations + lower-level feature service
workers -> feature.service + integrations + models
app.web -> app.core + app.database
app.web -X-> feature modules
config -X-> web/core/auth/models/database
parsers.core/implementations/utils -X-> parsers.api/service
feature.service -X-> feature.api.routes
```

### 4.5 Implementation Checklist

- [x] 1. 记录重构前 Git 状态、旧 import 扫描结果与可用测试基线。
- [x] 2. 创建 `app/core` 与 `app/web`，拆分应用异常/FastAPI handlers，迁移 shared schemas，拆分 DB/Auth dependencies，精简 `app/config`。
- [x] 3. 迁移 Auth API/schema/bootstrap/security，提取 `authenticate_user`，更新 Auth 测试。
- [x] 4. 迁移 Knowledge Base API/schema/service，更新直接消费方。
- [x] 5. 迁移 Search API/schema/service，更新 Knowledge Base 与 Embedding 依赖。
- [x] 6. 迁移 Embedding/MinIO 到 `app/integrations`，更新 parser、worker、search 消费方。
- [x] 7. 更新 `main.py`、测试 import 与 monkeypatch 路径，删除已空的旧包。
- [x] 8. 更新 parser 结构 Spec 中受影响的路径/边界描述，回写 Execute Log。
- [x] 9. 执行旧路径和反向依赖扫描，运行 compileall、Ruff `E/F/I`、相关测试与 OpenAPI 契约比对。
- [x] 10. 基于 Spec、diff 和验证结果执行三轴 Review，记录偏差与剩余风险。

### 4.6 Validation Plan

- `python -m compileall -q app tests`
- `python -m ruff check app tests --select E,F,I`
- parser/service/worker 现有目标测试。
- Auth/KB/Search/Document API 测试（外部 PostgreSQL/Redis/MinIO 不可用时如实记录）。
- `rg` 扫描旧 `app.routers/app.schemas/app.services/app.deps/app.config.{schemas,exceptions,dependencies}` 路径。
- 静态扫描 `app.web -> app.auth|knowledge_bases|search|parsers` 反向依赖。
- 对比重构前后 FastAPI OpenAPI 的 paths、methods、required fields 与 response model 形状。

### 4.7 Rollback and Safety

- 不执行 `git clean`、`git reset --hard` 或覆盖性 checkout。
- 不自动 stage/commit。
- 以模块为单位小步迁移，每批完成后编译与扫描。
- 发现需要改变 HTTP/数据库/业务行为时停止执行，先回到 Plan 更新 Spec。
- 现有 parser 重构和无关 dirty worktree 文件均视为用户内容予以保留。

## 4.8 Spec Review Notes

| Check | Verdict | Evidence |
|---|---|---|
| Requirement clarity & acceptance | PASS | Goal、In/Out Scope 与 9 条可验收标准已定义 |
| Plan executability | PASS | 文件迁移、签名、依赖规则和 10 步 checklist 已列明 |
| Risk / rollback readiness | PASS | 已限定行为边界、RQ 入口、dirty worktree 与非破坏性操作 |

- **Readiness Verdict**: GO（Advisory）
- **Risks & Suggestions**: 最大风险是 import 路径遗漏和 FastAPI 导入副作用，通过旧路径扫描、compileall 和 OpenAPI 对比控制。
- **Phase Reminders**: Execute 后补充实际测试数据、Review Matrix 与 Plan-Execution Diff。

### 4.9 Decision Log

- 2026-07-24：用户确认顶层共享层不使用 `app/api` 命名。调整为 `app/web` 承载 HTTP/FastAPI 基础，`app/core/exceptions.py` 承载框架无关应用异常；业务模块内部 `api` 职责不变。

## 5. Execute Log

- [x] Step 1: 已记录重构前基线。
  - Git：工作区已包含未提交的 parser 结构重构、相关测试/Spec 以及 `AGENT.md`、`CLAUDE.md`、Word 文档和 `tools/` 等用户改动；后续必须全部保留。
  - 旧 import 计数：`app.routers=2`、`app.schemas=5`、`app.services=9`、`app.deps=5`、`app.config.schemas=6`、`app.config.exceptions=8`、`app.config.dependencies=1`。
  - 可用测试：`python -m pytest tests/test_parsers tests/test_parser_asset_service.py tests/test_parser_hardening_service.py tests/test_parse_document_worker.py tests/test_parser_migration.py -q` -> `162 passed, 2 warnings`；另有 pytest-asyncio 未设默认 fixture loop scope 警告。
  - OpenAPI 基线：`/api/auth/login`、`/api/auth/me`、`/api/v1/kb`、`/api/v1/kb/{kb_id}`、`/api/v1/kb/{kb_id}/documents`、`/api/v1/kb/{kb_id}/documents/{doc_id}`、`/api/v1/kb/{kb_id}/search`、`/health`。
  - 环境前置：当前 `POSTGRES_DSN` 为空时应用 import 会失败；OpenAPI 基线使用不建立连接的合法占位 DSN 生成。
  - 已知警告：Starlette `multipart` PendingDeprecationWarning；pytest-asyncio 自定义 `event_loop` fixture DeprecationWarning。
- [x] Step 2: 创建 `app/core` 与 `app/web`；将框架无关异常、FastAPI handlers、HTTP schemas、DB/Auth dependencies 按所有者拆分；`app/config` 只保留 settings/logging。
- [x] Step 3: Auth 迁入 `api/service/security`；新增 `authenticate_user(db, email, password) -> User`，路由仅负责 HTTP 输入/输出与 token 响应装配。
- [x] Step 4: Knowledge Base 路由、schema 与 service 迁入 `app/knowledge_bases`，业务函数签名不变。
- [x] Step 5: Search 路由、schema 与 service 迁入 `app/search`；SQL 仅为通过 E501 做等价换行。
- [x] Step 6: Embedding/MinIO 迁入 `app/integrations`，parser、search、worker 已改用新路径。
- [x] Step 7: `main.py` 已按新模块装配路由与 handler；顶层 `routers/schemas/services` 和 `deps.py` 已删除；RQ `run_parse_document` 路径保持不变。
- [x] Step 8: parser 结构 Spec 与 backend 项目 CodeMap 已同步当前 Web/Core/Integrations 边界。
- [x] Step 9: 验证完成。
  - `python -m compileall -q app tests` -> PASS。
  - `python -m ruff check app tests --select E,F,I` -> `All checks passed`。
  - 旧 import 扫描 -> `legacy_imports=0`；`app/routers`、`app/schemas`、`app/services` -> 均不存在。
  - 反向依赖扫描 -> `web_reverse_dependencies=0`、`config_reverse_dependencies=0`、`service_to_routes=0`、`parser_lower_reverse_dependencies=0`。
  - 主回归 -> `162 passed, 2 warnings`。
  - Auth 密码/JWT -> `2 passed`；当前 Python 环境补装项目已声明的 `argon2-cffi`，未修改依赖文件。
  - Auth service 成功/拒绝分支临时校验 -> PASS。
  - 全量测试收集 -> `177 tests collected`，无 import/collection 错误。
  - OpenAPI -> 8 paths、9 methods、19 component schemas，与基线一致；上传 `file` 仍必填，`parser_engine` 仍默认 `builtin`。
  - `git diff --check -- backend/app backend/tests` -> PASS（仅有现有 LF/CRLF 提示）。
  - 未执行依赖 PostgreSQL/Redis/MinIO/worker/Embedding 的 13 个全链路用例；当前环境不具备其运行前置。
- [x] Step 10: 完成三轴 Review，结论 PASS。

## 6. Review Verdict

| Axis | Key Checks | Verdict | Evidence |
|---|---|---|---|
| Spec Quality & Requirement Completion | Goal/In-Scope/Acceptance 完整；目标目录、所有权与保留边界均完成 | PASS | 顶层旧包不存在；新目录与 §4.1 一致；OpenAPI 与基线一致 |
| Spec-Code Fidelity | 文件迁移、签名、依赖规则、checklist 与行为保持 | PASS | `authenticate_user` 签名一致；RQ 入口未移动；4 项反向依赖扫描为 0；旧 import 为 0 |
| Code Intrinsic Quality | 正确性、可维护性、导入副作用、测试、关键回归风险 | PASS | compileall/Ruff PASS；162 主回归 + 2 Auth 单测 PASS；177 用例收集 PASS；10 个新模块导入 PASS |

- **Overall Verdict**: PASS
- **Blocking Issues**: None。
- **Regression risk**: Medium-Low（仓库内路径和 HTTP 契约已验证；仓库外旧 import 和未运行的外部集成链路仍是剩余风险）。
- **Follow-ups**: 外部消费者需迁移旧内部 import；在完整基础设施环境中可补跑 13 个 API/DB/worker 全链路用例。

## 7. Plan-Execution Diff

- 用户在 Execute 开始后要求切换 Batch Override，Checklist 2-10 一次执行完成。
- Ruff 对移动后文件自动整理 import，并对 Search SQL 做等价换行；无逻辑变更。
- 为执行项目已有 Auth 密码测试，在当前 Python 环境安装已声明的 `argon2-cffi`；`pyproject.toml` 未变。
- 未引入旧 import 兼容 shim，未移动 ORM 或 RQ job 入口，未修改 HTTP/数据库/业务契约。
- 计划内的外部全链路测试因环境前置不可用而未执行；改以全量收集、目标回归、导入检查与 OpenAPI 契约断言覆盖本次结构风险。

## 8. Archive Record

- Pending Review completion.
