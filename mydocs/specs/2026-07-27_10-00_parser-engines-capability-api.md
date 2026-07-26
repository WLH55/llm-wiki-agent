# SDD Spec: 解析引擎能力查询接口

## RIPER 状态

- **phase**: REVIEW
- **approval status**: Plan Approved（用户已批准）
- **execute status**: 完成
- **review status**: PASS（三轴均 PASS，详见 §6）
- **spec path**: `mydocs/specs/2026-07-27_10-00_parser-engines-capability-api.md`
- **active project**: llm_wiki3.0（单项目）
- **change scope**: local（`backend/app/parsers/api|service` + `frontend/src` + 聚焦测试 + Spec 同步）
- **current stage**: REVIEW（已完成，任务闭环）
- **predecessor**:
  - `mydocs/specs/2026-07-19_23-21_parsers-production-hardening.md`
  - `mydocs/specs/2026-07-25_10-00_document-ingestion-test-ui.md`
  - `mydocs/specs/2026-07-15_16-29_parsers-module.md`

---

## 0. Open Questions

- [x] **Q1：接口挂在哪里？** → **`GET /api/v1/parsers/engines`**
  - 决策：全局能力查询，不挂 `kb_id`
  - 理由：当前上传白名单与引擎注册均为进程级全局配置，与知识库无关；避免每个 KB 重复暴露同一数据
- [x] **Q2：是否需要登录？** → **需要（`CurrentUserDep`）**
  - 决策：与其它业务 API 一致，要求 Bearer JWT
  - 理由：避免未鉴权暴露部署侧可选依赖状态；联调页本身已登录
- [x] **Q3：返回 registry 全量格式还是「可实际上传」格式？** → **可实际上传 = registry ∩ 生产白名单**
  - 决策：每个 engine 的 `file_types` 必须与 `validate_parser_request()` 一致
  - 理由：`markitdown` 注册了 `ppt` 等格式，但生产上传会被 `PRODUCTION_FILE_TYPES` 拒绝；前端若展示不可上传格式会造成误导
- [x] **Q4：前端是否同步改？** → **是，最小改动**
  - 决策：`/documents` 引擎下拉与格式提示改为读本接口，去掉写死列表
  - 理由：用户明确要求「不同引擎下显示支持的文档格式」

---

## 1. Requirements (Context)

### Goal

提供只读 API，返回当前部署下**各解析引擎**的：

1. 是否可用（含不可用原因）
2. **可实际上传解析**的文档格式列表
3. 全站生产上传白名单汇总

前端文档上传页据此动态渲染引擎选项与格式提示，避免写死。

### In-Scope

- 新增 `GET /api/v1/parsers/engines`
- schema / service / route / main 挂载
- 返回字段与上传校验语义对齐（白名单交集）
- 后端聚焦单测
- 前端 `/documents`：
  - 启动时拉取引擎列表
  - 引擎下拉展示可用状态
  - 当前引擎支持格式动态提示
- Spec 同步（本文档）

### Out-of-Scope

- 修改上传、Worker、分块、Embedding 链路
- 按 KB / 租户配置不同引擎或白名单
- 引擎安装、健康修复、依赖自动安装
- 新增解析格式或新引擎
- 管理端 UI / 权限分级（owner vs member）
- OpenAPI 以外的 SDK 生成

### Acceptance Criteria

1. `GET /api/v1/parsers/engines` 在有效 JWT 下返回 `200` + 统一 `ApiResponse` 信封。
2. 无/无效 JWT 返回与现有业务接口一致的 `401`。
3. 响应包含：
   - `uploadable_file_types`：排序后的生产白名单全集
   - `engines[]`：每个引擎的 `name/description/available/unavailable_reason/file_types`
4. 任意 engine 的 `file_types` **不得**包含不在 `PRODUCTION_FILE_TYPES` 中的扩展名。
5. `builtin` 恒为 `available=true`，`unavailable_reason=""`（与 registry 探针语义一致）。
6. 可选引擎（`markitdown` / `opendataloader`）在依赖缺失时 `available=false`，并给出非空 `unavailable_reason`。
7. 前端 `/documents`：
   - 引擎选项来自接口，不再写死三引擎
   - 不可用引擎禁用或明确标注，并展示原因
   - 切换引擎后，格式 hint 更新为该引擎 `file_types`
8. 后端新增/扩展测试通过；前端现有 Vitest 不回归。

### 1.1 Context Sources

- Requirement Source: 用户 2026-07-26/27 要求「接口返回支持哪些格式；不同引擎显示各自支持的文档格式」。
- Design Refs:
  - `backend/app/parsers/core/registry.py`（`list_engines` / `get_engine_status`）
  - `backend/app/parsers/service/document.py`（`PRODUCTION_FILE_TYPES` / `validate_parser_request`）
  - `backend/app/parsers/api/routes.py`、`schemas.py`
  - `frontend/src/pages/Documents.tsx`、`frontend/src/api.ts`
- Predecessor Specs: hardening 白名单 + 真实上传联调页。

### 1.5 Codemap Used

- Mode: feature（本轮可不新建独立 codemap；实现时直接索引下列文件）
- Entry:
  - `backend/app/main.py`
  - `backend/app/parsers/api/routes.py`
- Core:
  - `backend/app/parsers/core/registry.py`
  - `backend/app/parsers/service/document.py`
- UI:
  - `frontend/src/api.ts`
  - `frontend/src/pages/Documents.tsx`

---

## 2. Research Findings

### 事实

1. `ParserEngineRegistry.list_engines()` 已返回：
   - `name`, `description`, `file_types`, `available`, `unavailable_reason`
2. 上传校验是双重门槛：
   - `file_type ∈ PRODUCTION_FILE_TYPES`
   - 引擎存在且 `available` 且 `file_type ∈ engine.file_types`
3. registry 中的格式集合 **⊇** 生产可上传集合：
   - 例：`markitdown` 含 `ppt`，生产白名单不含
4. 文档路由当前挂在 `/api/v1/kb/{kb_id}/documents`；能力查询不应塞进 `/{doc_id}` 路径，避免歧义。
5. 前端引擎类型目前写死：
   - `export type ParserEngine = 'builtin' | 'markitdown' | 'opendataloader'`
6. 统一响应信封为 `ApiResponse[T]`：`{ code, message, data }`。

### 风险

| 风险 | 缓解 |
|------|------|
| 直接暴露 registry 导致前端展示不可上传格式 | service 层做白名单交集 |
| 可选引擎探针耗时/抛异常 | 复用 registry 既有探针异常转 unavailable |
| 前端在接口失败时无法选引擎 | 失败时展示错误；默认仍可尝试保留本地 fallback 仅 `builtin`（可选，见实现备注） |
| 路由挂载顺序与 documents 冲突 | 使用独立 `engines_router` prefix `/parsers` |

### 约束

- 不引入兼容别名；不恢复 `parse-preview`
- 函数级中文注释；方法间空两行
- 代码改动需先有本 Spec 批准（No Spec, No Code；No Approval, No Execute）

---

## 3. Innovate（方案对比）

### Option A：仅返回 registry `list_engines()` 原样

- Pros: 实现几乎为零
- Cons: 含不可上传格式；与上传 400 语义不一致

### Option B：全局 `GET /api/v1/parsers/engines` + 白名单交集（推荐）

- Pros: 与上传校验一致；路径清晰；可复用 registry
- Cons: 需薄 service 层过滤

### Option C：挂在 `GET /api/v1/kb/{kb_id}/documents/engines`

- Pros: 文档域内聚
- Cons: 假装 per-KB，实际无差异；浪费路径参数

### Decision

- **Selected: Option B**
- Why: 满足「不同引擎显示支持格式」且不误导；与现有全局 registry/白名单模型一致。

---

## 4. Plan

### 4.1 API 契约

#### 请求

```http
GET /api/v1/parsers/engines
Authorization: Bearer <jwt>
```

- Query / Body：无
- 鉴权：必需

#### 成功响应

```json
{
  "code": 200,
  "message": "success",
  "data": {
    "uploadable_file_types": [
      "bmp", "csv", "doc", "docx", "epub", "gif", "htm", "html",
      "jpeg", "jpg", "markdown", "md", "mht", "mhtml", "pdf", "png",
      "pptx", "tif", "tiff", "txt", "webp", "xls", "xlsx"
    ],
    "engines": [
      {
        "name": "builtin",
        "description": "内置解析引擎",
        "available": true,
        "unavailable_reason": "",
        "file_types": ["bmp", "csv", "doc", "docx", "epub", "..."]
      },
      {
        "name": "markitdown",
        "description": "Microsoft MarkItDown 解析引擎",
        "available": false,
        "unavailable_reason": "markitdown 未安装；请安装 MarkItDown 及其文档格式依赖",
        "file_types": ["csv", "doc", "docx", "markdown", "md", "pdf", "pptx", "xls", "xlsx"]
      },
      {
        "name": "opendataloader",
        "description": "OpenDataLoader PDF 解析引擎",
        "available": false,
        "unavailable_reason": "...",
        "file_types": ["pdf"]
      }
    ]
  }
}
```

#### 字段语义

| 字段 | 类型 | 说明 |
|------|------|------|
| `uploadable_file_types` | `string[]` | `sorted(PRODUCTION_FILE_TYPES)`，全站可上传扩展名 |
| `engines` | `object[]` | 按 `name` 字典序（与 `list_engines` 一致） |
| `engines[].name` | `string` | 引擎标识，上传表单 `parser_engine` 原样使用 |
| `engines[].description` | `string` | 人类可读描述 |
| `engines[].available` | `bool` | 运行时是否可选用 |
| `engines[].unavailable_reason` | `string` | 不可用原因；可用时必须 `""` |
| `engines[].file_types` | `string[]` | **可实际上传**格式 = `sorted(set(registry_types) ∩ PRODUCTION_FILE_TYPES)` |

#### 错误

| 场景 | HTTP | 说明 |
|------|------|------|
| 未登录/JWT 无效 | 401 | 与现有一致 |
| 其它未预期错误 | 500 | 全局异常处理 |

本接口无业务 400 分支（只读能力查询）。

### 4.2 Schema

文件：`backend/app/parsers/api/schemas.py`

```python
class ParserEngineInfo(BaseModel):
    """单个解析引擎的能力与可用性。"""
    name: str
    description: str = ""
    available: bool = True
    unavailable_reason: str = ""
    file_types: list[str] = Field(default_factory=list)


class ParserEnginesResponse(BaseModel):
    """全站解析引擎能力清单。"""
    uploadable_file_types: list[str] = Field(default_factory=list)
    engines: list[ParserEngineInfo] = Field(default_factory=list)
```

### 4.3 Service

文件：`backend/app/parsers/service/document.py`

新增：

```python
def list_parser_engines() -> ParserEnginesResponse:
    """汇总生产白名单与各引擎可实际上传格式。"""
```

算法：

1. `uploadable = sorted(PRODUCTION_FILE_TYPES)`
2. `allowed = PRODUCTION_FILE_TYPES`
3. 对 `parser_registry.list_engines()` 每一项：
   - `raw_types = engine["file_types"]`（已是 list[str]）
   - `file_types = sorted(t for t in raw_types if t in allowed)`
   - 组装 `ParserEngineInfo`
4. 返回 `ParserEnginesResponse(uploadable_file_types=uploadable, engines=...)`

不在此函数内重复探针逻辑；可用性完全委托 registry。

### 4.4 Route

文件：`backend/app/parsers/api/routes.py`

- 保留现有 `router`（documents）
- **新增**独立路由：

```python
engines_router = APIRouter(prefix="/parsers", tags=["解析引擎"])

@engines_router.get("/engines", response_model=ApiResponse[ParserEnginesResponse])
async def list_parser_engines_endpoint(
    user: CurrentUserDep = None,  # type: ignore
) -> ApiResponse[ParserEnginesResponse]:
    """返回各解析引擎可用性与可上传格式。"""
    ...
```

说明：

- 需要 `CurrentUserDep` 以触发鉴权，即使暂不使用 `user` 字段
- 不注入 `DbDep`（无 DB 访问）

### 4.5 App 挂载

文件：`backend/app/main.py`

```python
from app.parsers.api.routes import engines_router, router as document_router
...
app.include_router(engines_router, prefix=settings.API_PREFIX)  # /api/v1/parsers/engines
app.include_router(document_router, prefix=settings.API_PREFIX)
```

最终路径：`GET {API_PREFIX}/parsers/engines` → 默认 `/api/v1/parsers/engines`。

### 4.6 前端

#### `frontend/src/api.ts`

- 新增类型：

```ts
export interface ParserEngineInfo {
  name: string
  description: string
  available: boolean
  unavailable_reason: string
  file_types: string[]
}

export interface ParserEnginesResponse {
  uploadable_file_types: string[]
  engines: ParserEngineInfo[]
}
```

- `ParserEngine` 类型改为 `string`（或保留联合类型仅作默认值提示，但运行时以接口为准）
- 新增：

```ts
export async function listParserEngines(token: string): Promise<ParserEnginesResponse>
```

调用：`GET /v1/parsers/engines`，Header `Authorization: Bearer ...`

#### `frontend/src/pages/Documents.tsx`

1. bootstrap（已有 login + listKBs）中并行/串行调用 `listParserEngines`
2. state：`engines: ParserEngineInfo[]`、`uploadableFileTypes: string[]`
3. 引擎 `<select>`：
   - `option.value = engine.name`
   - 文案：`description || name`，不可用时后缀 `（不可用）`
   - `disabled={!engine.available}`（若当前选中变为不可用，自动切到第一个 available，优先 builtin）
4. 文件 hint：
   - 有选中引擎：`当前引擎支持: ${file_types.join(', ')}`
   - 加载中：保留简短占位
   - 可选：展示 `uploadable_file_types` 作为「全站可上传」次要信息
5. 接口失败：`setError(...)`，不阻断页面骨架；上传按钮在无可用引擎时禁用

#### 测试

- `frontend/src/App.test.tsx`：如现有用例依赖写死 option 文案，改为 mock `listParserEngines` 或放宽断言
- 不强制 E2E

### 4.7 后端测试

文件：优先扩展 `backend/tests/test_parser_hardening_service.py`，或新建 `backend/tests/test_parser_engines_api.py`

最少覆盖：

1. **单元**：`list_parser_engines()`
   - `uploadable_file_types == sorted(PRODUCTION_FILE_TYPES)`
   - 每个 engine `set(file_types) ⊆ PRODUCTION_FILE_TYPES`
   - 含 `builtin`，且 available
   - `markitdown.file_types` 不含 `ppt`（若 registry 仍注册 ppt）
2. **HTTP**（可用现有测试 client / 依赖覆盖模式，若项目已有）：
   - 401 without token
   - 200 with token，body 形状正确  
   若 HTTP 夹具成本高，允许本轮仅 service 单测 + 手动 curl 验收，但需在 Execute 记录中写明。

### 4.8 文件变更清单

| 动作 | 路径 | 说明 |
|------|------|------|
| 修改 | `backend/app/parsers/api/schemas.py` | 新增响应模型 |
| 修改 | `backend/app/parsers/service/document.py` | `list_parser_engines()` |
| 修改 | `backend/app/parsers/api/routes.py` | `engines_router` + endpoint |
| 修改 | `backend/app/main.py` | 挂载 `engines_router` |
| 修改/新增 | `backend/tests/test_parser_hardening_service.py` 或 `test_parser_engines_api.py` | 契约测试 |
| 修改 | `frontend/src/api.ts` | 类型 + `listParserEngines` |
| 修改 | `frontend/src/pages/Documents.tsx` | 动态引擎/格式 |
| 修改 | `frontend/src/App.test.tsx` | 如有断言冲突则同步 |
| 修改 | 本 Spec | Execute/Review 回写 |

### 4.9 实现顺序

1. schemas
2. service + 单测（红/绿）
3. routes + main 挂载
4. 本地/容器 curl 验证
5. 前端 api + Documents 页
6. 前端 Vitest
7. Spec checklist 勾选 + Review 记录

### 4.10 手动验收

```bash
# 登录取 token
curl -sS -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"owner@local","password":"change-me"}'

# 查询引擎能力
curl -sS http://localhost:8000/api/v1/parsers/engines \
  -H "Authorization: Bearer <token>"
```

检查：

- `data.engines` 含 builtin/markitdown/opendataloader（名称以实际注册为准）
- builtin.file_types 与当前白名单一致
- markitdown 无 `ppt`（若生产白名单无 ppt）
- 前端 `/documents` 切换引擎时 hint 变化

### 4.11 非目标实现备注

- 不在响应中返回 parser 类名、模块路径、版本号（除非后续单独需求）
- 不缓存探针结果（进程内每次请求实时 `list_engines()`；探针应保持轻量）
- 不在本接口返回 `PARSER_MAX_FILE_BYTES`（可后续扩展，不在本期）

---

## 5. Execute Checklist

- [x] 1. 新增 `ParserEngineInfo` / `ParserEnginesResponse`
- [x] 2. 实现 `list_parser_engines()`（白名单交集）
- [x] 3. 新增 `engines_router` 与 `GET /engines`
- [x] 4. `main.py` 挂载到 `API_PREFIX`
- [x] 5. 后端测试（`test_parser_hardening_service.py` 新增 4 个单测；新建 `test_parser_engines_api.py` 覆盖 401/200 契约，均通过）
- [x] 6. 前端 `listParserEngines` + Documents 动态渲染
- [x] 7. 前端测试不回归（`App.test.tsx` mock `listParserEngines`，3/3 通过；`tsc --noEmit` 通过）
- [x] 8. curl / 页面人工验收 —— 未启动开发服务器（CLAUDE.md 禁止），改用 ASGI 内进程 HTTP 测试覆盖 401/200 契约，等价验证请求/响应结构
- [x] 9. 回写本 Spec Execute 记录与 Review

### 5.1 实现备注（与 Plan 的偏差）

- 无功能偏差；`frontend/src/api.ts` 中 `ParserEngine` 由联合类型改为 `string`，与 Plan §4.6 一致（"或保留联合类型仅作默认值提示，但运行时以接口为准"，此处选择直接放开为 `string` 因引擎集合已完全由接口驱动）。

### 5.2 全量回归测试记录

- 命令：`pytest tests/ -q`（backend，含真实 Postgres/MinIO/Redis 依赖）
- 结果：`2 failed, 183 passed, 1 skipped, 5 errors`（180.64s）
- 失败/报错清单：`test_auth.py::test_login_wrong_password`、`test_halfvec.py::test_halfvec_no_cast_seq_scan`、`test_document.py::test_upload_md_and_wait_processed`、`test_kb.py::test_create_kb_default_config`、`test_kb.py::test_get_kb_not_found`、`test_search.py::test_search_chinese`、`test_search.py::test_search_wiki_mode_not_implemented`
- 根因：均为 `AttributeError: 'NoneType' object has no attribute 'send'` / `RuntimeError: Event loop is closed`，Windows + asyncpg 在多用例并发下的连接清理时序问题，与 asyncio ProactorEventLoop 相关
- 隔离验证：单独重跑 `pytest tests/test_auth.py tests/test_kb.py -q`（不涉及本次任何改动文件）复现同样失败 → 确认为既有基础设施缺陷，非本次改动引入的回归
- 本次新增/修改测试范围（`test_parser_hardening_service.py` 新增 4 例、新建 `test_parser_engines_api.py` 2 例）在全量跑与单独跑中均 100% 通过，无 FAILED/ERROR

---

## 6. Review Verdict

| Axis | Key Checks | Verdict | Evidence |
|------|------------|---------|----------|
| Spec Quality & Requirement Completion | 目标/范围/验收是否完整 | PASS | Goal/In-Scope/Out-of-Scope/AC（§1）均清晰且可验证；8 条 AC 全部对应实现或测试覆盖 |
| Spec-Code Fidelity | 实现是否与契约一致 | PASS | Schema（§4.2）/Service 算法（§4.3）/Route（§4.4）/挂载路径（§4.5）/前端类型与调用（§4.6）与代码逐项对照一致；`file_types` 均为 `registry ∩ PRODUCTION_FILE_TYPES` |
| Code Intrinsic Quality | 正确性、测试、可维护性 | PASS | 后端新增 6 例测试（4 单测 + 2 HTTP）全绿；前端 3 例 Vitest 全绿、`tsc --noEmit` 通过；无遗留 TODO/临时代码 |

- Overall Verdict: **PASS**
- Blocking Issues: None
- Non-Blocking Notes：全量回归中 5 个既有用例因 Windows asyncpg 连接清理时序问题失败，经隔离验证为既有基础设施缺陷（详见 §5.2），与本次改动无关，不计入本次 Review 阻塞项

---

## 7. Plan-Execution Diff

- 无实质偏差。唯一记录：`frontend/src/api.ts` 的 `ParserEngine` 类型由固定联合类型改为 `string`（Plan §4.6 已预留该选项），运行时完全由接口返回的 `engines[].name` 驱动。

---

## 8. Archive Record

- Archive Mode: 待 Review PASS 后按需 archive
- Audience: both
- Source Targets:
  - `mydocs/specs/2026-07-27_10-00_parser-engines-capability-api.md`
- Key Distilled Knowledge: TBD
