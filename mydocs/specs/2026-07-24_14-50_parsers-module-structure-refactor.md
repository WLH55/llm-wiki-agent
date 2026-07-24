# SDD Spec: parsers 模块结构重构

## RIPER 状态

- **phase**: REVIEW
- **approval status**: `Plan Approved`（2026-07-24，用户确认“按照你推荐的来”）
- **execution mode**: 直接增量重构；用户明确不使用 TDD 和 subagent-driven-development
- **execute status**: 已完成
- **review status**: PASS
- **spec path**: `mydocs/specs/2026-07-24_14-50_parsers-module-structure-refactor.md`
- **active project**: llm_wiki3.0
- **change scope**: local（backend parser 模块及其直接调用方、测试）

## 1. Goal

将 `backend/app/parsers` 从平铺结构整理为按职责分层的模块，使 HTTP 接口、业务服务、核心抽象、格式实现和工具函数边界清晰，同时保持现有 HTTP API、数据库结构和解析行为不变。

### In Scope

- parser 专属数据契约迁入 `app.parsers.schemas`。
- parser 专属异常迁入 `app.parsers.errors`。
- 文档上传/状态 API 迁入 `app.parsers.api`。
- 文档解析业务、派发、图片资产服务迁入 `app.parsers.service`。
- 基础抽象、责任链、文档模型、注册表迁入 `app.parsers.core`。
- 各格式 parser 迁入 `app.parsers.implementations`。
- 无业务状态的转换、压缩包、媒体和网络工具迁入 `app.parsers.utils`。
- 更新应用入口、worker、测试及模块内部 imports。
- 保留 `app.parsers` 顶层公共导出。

### Out of Scope

- 不修改 HTTP 路径、请求字段或响应结构。
- 不修改数据库表和 Alembic 迁移。
- 不增加或删除文件格式、parser engine。
- 不改变解析、分块、Embedding 或 MinIO 行为。
- 不处理当前环境缺少 `ebooklib`、`xlwt` 等依赖的问题。

## 2. Target Structure

```text
app/parsers/
├── api/                 # FastAPI 路由与 API schemas
├── service/             # 上传、状态、派发、图片资产业务
├── core/                # BaseParser、责任链、Document、Registry
├── implementations/     # 文件格式与第三方引擎实现
├── utils/               # 编码、Office、压缩包、媒体、网络工具
├── schemas.py           # ParseErrorCode、ParseResult、ParseLimits
├── errors.py            # ParserError、ParseDispatchError、ParserAssetError
└── __init__.py          # 稳定公共导出与默认注册
```

### Boundary Decisions

- `app.web.schemas` 只保留全局 HTTP 响应契约，不引入 parser 领域错误码。
- `app.core.exceptions` 保存框架无关应用异常；`app.web.exception_handlers` 负责 FastAPI 异常响应转换。
- `app.parsers.schemas` 保存 parser 领域数据契约和错误码。
- `app.parsers.errors` 保存 parser 内部异常；其异常由 service/worker 捕获后转换为 HTTP 或持久化状态。
- `app.models.document.Document` 是数据库模型，仍保留在全局 models；`app.parsers.core.document.Document` 是 parser 输出模型。

## 3. File Changes

### API

- `app/routers/document.py` -> `app/parsers/api/document.py`
- `app/schemas/document.py` -> `app/parsers/api/schemas.py`

### Service

- `app/services/document_service.py` -> `app/parsers/service/document.py`
- `app/services/parser_asset_service.py` -> `app/parsers/service/asset.py`
- `app/parsers/dispatch.py` -> `app/parsers/service/dispatch.py`

### Core and Contracts

- `app/parsers/base.py` -> `app/parsers/core/base.py`
- `app/parsers/chain.py` -> `app/parsers/core/chain.py`
- `app/parsers/document.py` -> `app/parsers/core/document.py`
- `app/parsers/registry.py` -> `app/parsers/core/registry.py`
- 拆分 `app/parsers/result.py` 为 `app/parsers/schemas.py` 与 `app/parsers/errors.py`。

### Implementations

- 所有 `*_parser.py` 及具体格式 parser 移入 `app/parsers/implementations/`，文件名去掉不必要的 `_parser` 后缀。

### Utils

- `_utils/endecode.py` -> `utils/encoding.py`。
- `excel_convert.py`、`xlsx_merge.py`、`xlsx_repair.py`、`pptx_media.py`、`web_fetcher.py` 移入 `utils/`。

## 4. Implementation Checklist

- [x] 1. 创建目标包与 `__init__.py`。
- [x] 2. 拆分 parser schemas/errors，更新错误依赖。
- [x] 3. 迁移 core 并更新实现层引用。
- [x] 4. 迁移 utils 与 implementations 并更新交叉引用。
- [x] 5. 迁移 service 和 api，更新 main/worker 引用。
- [x] 6. 更新测试导入路径和 monkeypatch 目标。
- [x] 7. 保持 `app.parsers` 顶层公共 API。
- [x] 8. 运行可用测试、导入检查与 Ruff。
- [x] 9. 审查行为一致性和残留旧路径。
- [x] 10. 回写 Execute Log、Review Verdict 和 Plan-Execution Diff。

## 5. Acceptance Criteria

1. `app.parsers` 下存在 `api/service/core/implementations/utils` 五个职责包。
2. `ParseErrorCode` 位于 `app.parsers.schemas`，不位于 `result.py` 或 `config.schemas`。
3. `core/exceptions.py` 与 `web/exception_handlers.py` 不承载 parser 内部异常。
4. `main.py` 从 `app.parsers.api` 注册文档路由。
5. worker 从 `app.parsers.service` 调用派发与图片服务。
6. 全仓不再引用已迁移的旧模块路径。
7. HTTP endpoint、请求/响应字段和 parser engine 注册保持不变。
8. 可运行测试通过；缺失外部依赖导致的验证缺口如实记录。

## 6. Validation

- `python -m compileall -q app tests`：PASS。
- parser/service/asset/worker/migration 目标测试：`162 passed`。
- Ruff `E/F/I`（parser、main、worker 和相关测试）：PASS。
- 旧模块路径扫描：0 处残留。
- 底层 `core/implementations/utils` 反向依赖 `api/service` 扫描：0 处。
- OpenAPI 路径保持 `/api/v1/kb/{kb_id}/documents` 和 `/api/v1/kb/{kb_id}/documents/{doc_id}`。
- OpenAPI multipart 保持 `file` 必填、`parser_engine` 默认 `builtin`。
- 顶层公共导入 `ParseErrorCode/ParseResult/registry`：PASS。
- 为恢复项目声明的测试运行环境，本机安装了 `ebooklib`、`xlwt`、`trafilatura`、`playwright`、`asyncpg`；未修改依赖清单。
- 测试保留 2 条既有弃用警告：Starlette `multipart` 导入和 pytest-asyncio 自定义 event loop fixture。

## 7. Review Verdict

| Axis | Verdict | Evidence |
|---|---|---|
| Spec Quality & Requirement Completion | PASS | 五个职责包、schemas/errors 边界和验收条件均已完成 |
| Spec-Code Fidelity | PASS | 所有迁移路径与 checklist 对齐；HTTP/DB/engine 行为未变 |
| Code Intrinsic Quality | PASS | 162 tests、Ruff E/F/I、编译和依赖方向检查均通过 |

- **Overall Verdict**: PASS
- **Blocking Issues**: None
- **Residual Risk**: 这是大规模模块路径调整；仓库外若存在直接导入旧内部路径的脚本，需要同步迁移。仓库内调用已全部更新。

## 8. Plan-Execution Diff

- 用户在执行前明确取消 TDD 和 subagent-driven-development，采用现有测试回归保护。
- 原计划 `api/__init__.py` 导出 router；测试发现这会在导入 API schemas 时提前初始化数据库依赖，改为无副作用包入口，由 `main.py` 显式导入 `api.document.router`。
- 2026-07-24 后续结构重构将全局 HTTP/应用异常边界迁入 `app.web` 与 `app.core`；详见 `mydocs/specs/2026-07-24_15-30_backend-directory-structure-refactor.md`。
- 原 `map_legacy_error` 从 result 模型中拆出后归入 `utils/error_mapping.py`，符合无状态工具职责。
- 仅整理 import 和超长行；未顺手现代化既有 `typing.List/Optional` 标注，避免扩大范围。
