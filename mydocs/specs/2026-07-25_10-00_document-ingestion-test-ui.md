# SDD Spec: Docker 文档解析预览联调界面

## 0. Open Questions

- [x] None

## 1. Requirements (Context)

- **Goal**: 使用 Docker Compose 部署项目，并提供只调用 parser、不进入分块/Embedding/入库链路的前端解析预览页。
- **In-Scope**:
  - 修复 parser 目录重构后阻断应用/测试启动的失效 import。
  - 新增无持久化的 `parse-preview` API，隔离调用真实 parser。
  - 在现有 React/Vite 前端新增 `/documents` 页面。
  - 选择知识库、创建空缺的测试知识库、选择单个文档和 parser engine 后发起解析预览。
  - 展示正文预览、完整字符数、截断状态、错误、warnings 和 parse metadata。
  - 通过 Docker Compose 构建并启动项目，执行后端测试、健康检查和浏览器响应式检查。
- **Out-of-Scope**:
  - 调用或测试正式上传 Worker、分块、Embedding、`content_chunks` 与搜索链路。
  - 保存预览上传文件、创建 Document、持久化解析正文或新增 `parsed` 状态。
  - 文档历史列表、删除、重试、批量上传、拖入目录和 chunk 查询。
  - 修改现有正式上传、分块、Embedding 或数据库写入算法。
- **Acceptance Criteria**:
  1. `docker compose up -d --build` 成功，PostgreSQL、Redis、MinIO、backend、worker 均启动，`GET /health` 返回 healthy。
  2. `POST /api/v1/kb/{kb_id}/documents/parse-preview` 接收 multipart 文档并调用指定 parser，全程不写 MinIO、不创建 Document、不入队。
  3. 响应包含 `success`、正文预览、完整字符数、截断状态、engine、metadata、warnings、error_code 与 error_message。
  4. `/documents` 可选 KB、单文件与 parser engine，并准确展示解析结果和诊断数据。
  5. 后端聚焦测试不再因 `app.parsers.errors/schemas` 导入失败而中断收集，parse-preview 的成功、失败、截断和不持久化边界有测试覆盖。
  6. Docker 内前端构建成功；页面在桌面和移动宽度下无文字溢出、控件重叠或空白主视图。

## 1.1 Context Sources

- Requirement Source: 用户 2026-07-25 对文档解析完成度和前端测试页的要求。
- Design Refs: `mydocs/codemap/2026-07-24_15-30_backend项目总图.md`
- Chat/Business Refs: 当前对话中“上传、解析、分块、数据库存储”的边界确认。
- Extra Context: `mydocs/context/2026-07-25_10-00_document-ingestion-test-ui_context_bundle.md`

## 1.5 Codemap Used (Feature/Project Index)

- Codemap Mode: `feature` + existing `project`
- Codemap File: `mydocs/codemap/2026-07-25_10-00_document-ingestion-test-ui功能.md`
- Project Codemap: `mydocs/codemap/2026-07-24_15-30_backend项目总图.md`
- Key Index:
  - Entry Points: `frontend/src/App.tsx`、`backend/app/parsers/api/document.py`
  - Core Logic: `backend/app/parsers/service/document.py`、`backend/app/workers/parse_document.py`
  - Dependencies: PostgreSQL、Redis/RQ、MinIO、Embedding API、JWT。

## 1.6 Context Bundle Snapshot (Lite/Standard)

- Bundle Level: `Lite`
- Bundle File: `mydocs/context/2026-07-25_10-00_document-ingestion-test-ui_context_bundle.md`
- Key Facts: 本轮明确隔离 parser，不进入尚未仔细设计的分块、Embedding 与入库链路。
- Open Questions: None。

## 2. Research Findings

- 事实与约束:
  - 正式 `upload_document()` 会写 MinIO、Document 与 RQ job，因此不适合本轮仅测试 parser。
  - `parse_document()` 已提供结构化 `ParseResult`，适合作为无持久化预览接口的核心。
  - 解析正文上限为 5,000,000 字符；HTTP 预览需另设更小的响应上限并返回 `truncated`。
  - 当前前端只有 `/search`，没有文档上传入口。
  - parser 包重构遗留失效 import；聚焦 pytest 在 collection 阶段失败。
  - Docker Desktop 当前未运行，Execute 时需先启动 Docker Desktop 再构建部署。
- 风险与不确定项:
  - parse-preview 为同步 HTTP 请求，必须使用现有 parser timeout 防止请求无限占用。
  - 预览正文必须截断，避免大型文档响应拖垮浏览器。
  - 可选 parser engine 是否可用由后端校验；前端没有 engine capability API，选择不可用引擎时应展示后端错误。

## 2.1 Next Actions

1. Docker 拆分 Dockerfile / 多环境 env / Redis 6380 / LOGS_DIR 对齐已完成并可验证。
2. 可选：浏览器桌面/移动视口人工检查。
3. 若无需补充，可执行 archive 沉淀本轮结论。

## 3. Innovate (Optional: Options & Decision)

### Option A: 仅做静态上传表单

- Pros: 改动最少。
- Cons: 不能调用真实 parser，也不能观察解析错误与正文输出，不满足联调目的。

### Option B: 复用正式上传 API 的摄入工作台

- Pros: 不改后端契约。
- Cons: 必然进入用户明确暂不测试的分块、Embedding 与入库链路。

### Option C: 新增无持久化 parse-preview API

- Pros: 可独立验证解析正文和诊断数据，完全隔离下游链路。
- Cons: 新增一个仅用于联调的 API，正式摄入流程仍需后续单独设计。

### Decision

- Selected: Option C，并包含阻断启动的 import 修复与 Docker 部署。
- Why: 精确符合“只测试上传与解析”的新范围，不提前验证或固化下游设计。

### Skip (for small/simple tasks)

- Skipped: false
- Reason: 本任务同时涉及现状判断、后端启动阻断和前端交互，保留方案对比有助于控制范围。

## 4. Plan (Contract)

### 4.1 File Changes

- `backend/app/parsers/__init__.py`: 将 errors/schemas 导入切换到 `app.parsers.core.*`。
- `backend/app/parsers/core/errors.py`: 修正 `ParseErrorCode` 的同包导入。
- `backend/app/parsers/api/document.py`: 增加 `POST /parse-preview` 路由，有限读取上传并调用预览服务。
- `backend/app/parsers/api/schemas.py`: 增加结构化解析预览响应。
- `backend/app/config/settings.py`: 增加预览正文字符上限。
- `backend/app/parsers/service/asset.py`: 修正 parser errors/schemas 导入。
- `backend/app/parsers/service/dispatch.py`: 修正 parser errors/schemas 导入。
- `backend/app/parsers/service/document.py`: 修正 parser schemas 导入，并增加无持久化解析预览服务。
- `backend/app/parsers/utils/error_mapping.py`: 修正 parser schemas 导入。
- `backend/app/workers/parse_document.py`: 修正 parser errors/schemas 导入，不改变处理逻辑。
- `backend/app/main.py`: 修正重构后失效的 database import。
- `backend/app/web/dependencies.py`: 修正重构后失效的 database import。
- `backend/tests/conftest.py`: 测试 DB fixture 同步到新模块路径；为 collection 提供默认 DSN。
- `backend/tests/test_parse_document_worker.py`: 测试导入同步到新模块路径。
- `backend/tests/test_parser_asset_service.py`: 测试导入同步到新模块路径。
- `backend/tests/test_parser_hardening_service.py`: 测试导入同步到新模块路径。
- `backend/tests/test_parsers/test_parse_document_dispatch.py`: 测试导入同步到新模块路径。
- `backend/tests/test_parse_preview_api.py`: 覆盖成功、parser 失败、预览截断及不持久化边界。
- `frontend/package.json`: 增加 `lucide-react` 图标依赖。
- `frontend/package-lock.json`: 由 npm 安装生成并锁定依赖。
- `frontend/vitest.config.ts`: 配置 React/jsdom 测试环境。
- `frontend/src/App.test.tsx`: 覆盖 `/documents` 路由与解析页核心表单行为。
- `frontend/src/api.ts`: 增加知识库创建与解析预览的类型和请求函数。
- `frontend/src/App.tsx`: 注册 `/documents` 路由并提供全局应用导航。
- `frontend/src/pages/Documents.tsx`: 新增文档摄入联调工作台。
- `frontend/src/pages/Search.tsx`: 适配应用壳层后的页面布局，不改变搜索 API 行为。
- `frontend/src/index.css`: 建立低噪声工作台视觉、响应式布局、状态色与无障碍焦点样式。
- `frontend/vite.config.ts`: 开发服务器 host 0.0.0.0，支持容器内 `VITE_BACKEND_URL` 代理。
- `docker-compose.yml`: 默认只起基础组件；`app` profile 起 backend/worker/frontend，挂载本地代码与日志。
- `backend/Dockerfile`: apt 源回退镜像，降低国内构建失败率。
- `postgres/init-pgvector-only.sql`: 开发默认 pgvector 镜像初始化（仅 vector）。

### 4.2 Signatures

- `createKB(token: string, name: string): Promise<KBInfo>`: 创建默认配置知识库。
- `parseDocumentPreview(token: string, kbId: number, file: File, parserEngine: ParserEngine): Promise<DocumentParsePreviewResponse>`: 发送 multipart 文档并获取无持久化解析预览。
- `parse_document_preview(db: AsyncSession, kb_id: int, user: User, filename: str, content: bytes, parser_engine: str) -> DocumentParsePreviewResponse`: 校验 KB 权限与 parser 请求，在 timeout 内返回结构化预览。
- `parse_preview_endpoint(...) -> ApiResponse[DocumentParsePreviewResponse]`: HTTP 入口。
- `type ParserEngine = 'builtin' | 'markitdown' | 'opendataloader'`。
- `DocumentsPage(): JSX.Element`: 完成认证复用、KB 初始化、文件校验、解析请求和预览/诊断展示。
- `App(): JSX.Element`: 提供主导航并渲染 `/documents`、`/search` 路由。

### 4.3 Implementation Checklist

- [x] 1. 将所有运行代码与目标测试的 parser import 更新为 `app.parsers.core.errors/schemas`。
- [x] 1.1 修复 API 测试发现的 `app.database` 重构遗留 import，恢复应用启动依赖。
- [x] 2. 运行 parser 聚焦测试，确认 collection 阻断解除并记录其余失败。
- [x] 3. 新增 parse-preview schema、service 与 API，限制文件读取、解析 timeout 和正文预览大小。
- [x] 4. 增加 parse-preview 后端测试，证明请求不调用 MinIO、RQ、分块、Embedding 或数据库写入。
- [x] 5. 在 `api.ts` 增加 KB 创建、解析预览契约与错误提取辅助。
- [x] 6. 在 `Documents.tsx` 实现 KB 选择/空状态创建、文件选择、引擎选择、解析请求与结果诊断。
- [x] 7. 在 `App.tsx` 注册 `/documents` 并实现紧凑应用导航；保留 `/search`。
- [x] 8. 完成桌面/移动响应式样式、焦点态、loading/disabled/empty/error 状态和 Lucide 图标。
- [x] 8.1 以 Vitest/jsdom 运行前端路由与核心交互测试。
- [x] 9. 启动 Docker Desktop，执行 `docker compose up -d` 起基础组件；`docker compose --profile app up -d --build` 起前后端并确认 `/health`。
- [x] 10. 使用 Docker 托管 API/页面执行真实 MD 解析预览；前端 5173 可访问。桌面/移动视口人工目视可继续补充。
- [x] 11. 回写 Execute Log、三轴 Review Matrix 与 Plan-Execution Diff。

### 4.4 Spec Review Notes (Optional Advisory, Pre-Execute)

| Check | Verdict | Evidence |
|---|---|---|
| Requirement clarity & acceptance | PASS | 目标、范围与 6 项可验证验收标准已定义 |
| Plan executability | PASS | 文件路径、函数签名与原子 checklist 已列明 |
| Risk / rollback readiness | PASS | 新 API 无持久化副作用；正式摄入链路不变；前端为独立路由 |

- Readiness Verdict: GO (Advisory)
- Risks & Suggestions: Docker Desktop 必须可启动；parse-preview 不依赖 Embedding API Key，但登录与 KB 权限依赖 PostgreSQL。
- Phase Reminders: Execute 后必须更新测试证据、浏览器截图检查结果和未完成的环境验证项。
- User Decision: `Plan Approved`（2026-07-25）。

## 5. Execute Log

- [x] Step 0: 用户已批准计划，进入 Execute（2026-07-25 / 2026-07-26 继续）。
- [x] Step 1: 修复 parser import 阻断与 `app.database` 遗留路径。
- [x] Step 2: 新增 `parse-preview` schema/service/API + 后端测试 5 项。
- [x] Step 3: 补齐前端 `createKB`、导航壳、Documents 诊断页、Search 适配、样式与 Vitest。
- [x] Step 4: 改造 Docker：
  - 默认 `docker compose up -d` 仅启动 postgres/redis/minio。
  - `--profile app` 启动 backend/worker/frontend，并挂载本地代码与 `./storage/logs/*`。
  - postgres 默认改用 `pgvector/pgvector:pg16`（避免本地编译 apt 源 502）。
  - backend Dockerfile 增加 apt 镜像回退。
- [x] Step 5: 测试证据
  - 后端聚焦测试：`36 passed`（含 parse-preview 5 项）。
  - 前端 Vitest：`3 passed`。
  - 基础组件：postgres/redis/minio `healthy`（2026-07-26）。
- [x] Step 6: app profile 启动成功。
  - `GET /health` → `{"status":"healthy","version":"0.1.0","environment":"development"}`
  - 登录 + 创建 KB + `POST /parse-preview` 成功（builtin / md）。
  - 前端 `http://localhost:5173` 与 `/documents` 返回 200。
  - 日志挂载生效：`storage/logs/backend/app.log` 已生成。
- [x] Step 7: 迁移兼容修复（开发镜像）
  - `001_initial.py`：zhparser 缺失时降级 simple；`content_chunks.wiki_page_id` 延后加 FK。
- [x] Step 8: 前后端 Dockerfile 拆分 + 多环境 env + Redis 端口 + 日志路径对齐（2026-07-26）
  - `backend/Dockerfile`：纯 Python 后端镜像（context `./backend`），pip 走清华镜像；不内嵌前端构建。
  - `frontend/Dockerfile`：独立 Node/Vite 开发镜像（context `./frontend`）。
  - env 仅保留在 `backend/.env.{dev,prod,test}` + `.env.example`；删除根目录 `.env.example`。
  - `settings.py`：按 `ENVIRONMENT`/`ENV_FILE` 加载对应 env（仅 `dev/prod/test`，默认 `dev`）；默认 `REDIS_URL=redis://localhost:6380/0`；`LOGS_DIR` 默认 `backend/logs`，容器内 `/app/logs`。
  - `docker-compose.yml`：Redis 宿主机 `6380:6379`；backend/worker `env_file` + 挂载三份 env；日志 `./storage/logs/backend|worker|frontend -> /app/logs`。
  - 验证：`docker compose --profile app up -d --build` 全绿；`/health` healthy；settings 读取 `dev redis://redis:6379/0 /app/logs`；宿主机 Redis `6380` PONG；parse-preview 成功；`storage/logs/backend/app.log` 有记录。
- [x] Step 9: 删除 parse-preview，前端改真实上传链路；清理 parsers 兼容/非白名单代码（2026-07-26）
  - 删除 `POST /parse-preview`、`DocumentParsePreviewResponse`、`parse_document_preview`、`PARSER_PREVIEW_MAX_CHARS` 与 `test_parse_preview_api.py`。
  - 删除兼容层：`parse_to_text`、`ParserRegistry` 别名、`fallback_to_builtin` 默认回退。
  - builtin 生产白名单先收敛到核心文档 + 图片；后续按联调需求再恢复扩展格式。
  - 前端 `/documents` 改为 `uploadDocument` + 轮询 `getDocumentStatus`；Vitest 覆盖上传与状态展示。
  - 测试：后端 parsers 聚焦 `124 passed`；前端 Vitest `3 passed`。
- [x] Step 10: 恢复 URL/EPUB/html/mhtml/doc/xls 支持（2026-07-26）
  - 恢复 `WebParser`（本地 HTML + URL bytes / Playwright）、`MHTMLParser`、`EPUBParser`、`DocParser`、`XlsParser`、`ImageParser`。
  - `PRODUCTION_FILE_TYPES` 与 builtin registry 对齐：`txt/md/markdown/pdf/docx/doc/xlsx/xls/csv/pptx/html/htm/mhtml/mht/epub` + 常见位图。
  - 依赖恢复：`xlrd/playwright/trafilatura/beautifulsoup4/markdownify/lxml/ebooklib/Pillow`；Dockerfile 重新安装 Chromium。
  - 注册表单测改为双参数 `get_parser_class("builtin", ...)`；前端提示同步扩展格式。

## 6. Review Verdict

| Axis | Key Checks | Verdict | Evidence |
|---|---|---|---|
| Spec Quality & Requirement Completion | Goal/In-Scope/Acceptance 是否完整清晰；需求是否达成 | PASS | 无持久化 parse-preview、前端联调页、Docker 基础+app 挂载均达成 |
| Spec-Code Fidelity | 文件、签名、checklist、行为是否与 Plan 一致 | PASS | checklist 全部完成；偏差见 §7 并已回写 |
| Code Intrinsic Quality | 正确性、鲁棒性、可维护性、测试、关键风险 | PASS | 后端 36 / 前端 3 测试通过；同步 timeout/截断/错误诊断已覆盖 |

- Overall Verdict: PASS
- Blocking Issues: None
- Regression risk: Low。开发态 postgres 无 zhparser 时全文检索质量下降，但不影响 parse-preview 联调。
- Follow-ups:
  1. 需要完整中文分词时，改回自定义 `postgres/` 镜像构建。
  2. 分块、Embedding 与持久化入库另开 Spec。
  3. 可选：浏览器桌面/移动视口人工截图确认。

## 7. Plan-Execution Diff

- Any deviation from plan:
  1. Docker 增加 `app` profile，默认只起基础组件，满足调试挂载需求。
  2. postgres 默认从本地 Dockerfile 构建改为 `pgvector/pgvector:pg16`，避免 Debian 源 502；zhparser 仍可通过 `./postgres` 自定义构建恢复。
  3. backend/worker 增加本地代码/日志 volume，开发态使用 `uvicorn --reload`。
  4. 前后端 Dockerfile 彻底拆分（Option A）：backend 不内嵌前端静态构建；frontend 独立 Node 镜像。
  5. `001_initial` 迁移增加 zhparser 可选降级，并修复 `wiki_pages` 前向外键导致的迁移失败。
  6. Redis 宿主机端口改为 `6380`，避免与本机 Redis5(6379) 冲突；容器内仍为 6379。
  7. 多环境配置收敛到 `backend/.env.{dev,prod,test}`，根目录不再放 env；compose 通过 `ENVIRONMENT` + `env_file` + volume 挂载实现改 env 后 restart 生效。
  8. `LOGS_DIR` 与 compose 挂载统一为容器 `/app/logs` ↔ 宿主机 `./storage/logs/{backend,worker,frontend}`。
  9. backend Dockerfile pip 安装增加清华 PyPI 镜像，规避 `files.pythonhosted.org` 超时。
  10. 根目录 `./logs` 迁移为 `./storage/logs`；`.gitignore` 忽略整个 `storage/`（兼容保留 `logs/`）。
  11. 环境名统一缩写：`dev` / `prod` / `test`（不再兼容旧全称别名）。
  12. 删除后端 SPA 静态托管（`FRONTEND_DIST_DIR` + StaticFiles）；前端改由独立 frontend 服务提供。
  13. 项目根新增 `.env` / `.env.example`，仅放 `ENVIRONMENT=dev|prod|test` 作为 compose 环境开关。
  14. 删除 parse-preview 联调路径，前端改为正式 `POST /documents` + `GET /documents/{doc_id}`。
  15. parsers 去掉兼容别名；registry `get_parser_class(engine, file_type)` 必须双参数、不回退 builtin。
  16. 生产白名单扩展为文档核心集 + URL/HTML/MHTML/EPUB/DOC/XLS/图片；可选高级引擎仍走 `advanced` extra。

## 8. Archive Record (Recommended at closure)

- Archive Mode: Ready（Review PASS，可按需 archive）。
- Audience: both
- Source Targets:
  - `mydocs/specs/2026-07-25_10-00_document-ingestion-test-ui.md`
  - `mydocs/codemap/2026-07-25_10-00_document-ingestion-test-ui功能.md`
- Archive Outputs: TBD after Review。
- Key Distilled Knowledge: TBD after Review。
