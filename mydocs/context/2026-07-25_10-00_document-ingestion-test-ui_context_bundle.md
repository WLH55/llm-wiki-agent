# Context Bundle: 文档摄入联调界面

## Source Index

- 用户需求：确认文档解析模块完成边界，并编写前端界面测试上传与解析。
- 后端项目图：`mydocs/codemap/2026-07-24_15-30_backend项目总图.md`
- 本功能图：`mydocs/codemap/2026-07-25_10-00_document-ingestion-test-ui功能.md`
- 上传与状态 API：`backend/app/parsers/api/document.py`、`backend/app/parsers/api/schemas.py`
- 上传服务：`backend/app/parsers/service/document.py`
- Worker：`backend/app/workers/parse_document.py`
- 当前前端：`frontend/src/App.tsx`、`frontend/src/api.ts`、`frontend/src/pages/Search.tsx`
- 验证：`backend/tests/test_parse_document_worker.py`、`backend/tests/test_document.py`

## Requirement Snapshot

- 先通过 Docker Compose 部署项目，再提供真实调用后端 parser 的文档解析预览页，不做静态原型。
- 用户可选择知识库、选择文件、指定解析引擎并发起上传。
- 页面展示解析成功/失败、正文预览、完整字符数、截断状态、错误码、错误消息、warnings 和 parse metadata。
- 本轮请求不保存文件、不入队，不调用分块、Embedding、`content_chunks` 或搜索。
- 复用现有登录与知识库列表，确保权限链路真实。

## Confirmed Facts

- 用户明确要求本轮不测试分块、Embedding 与数据库写入。
- 后端当前没有独立 parser 联调 API；复用正式上传接口会不可避免地进入未评审的下游链路。
- 新增无持久化的 parse-preview API 是隔离测试 parser 的最小边界。
- parser 重构遗留 import 错误导致相关测试无法收集，必须先解除阻断才能联调。
- Docker 当前未启动，端到端结果尚未验证。

## Constraints

- 不改动现有正式上传与 Worker API 契约；仅新增 parse-preview API。
- 不新增 chunk 列表、文档列表、删除或重试接口。
- 保留现有 `/search` 页面和 JWT localStorage 行为。
- UI 需要桌面与移动端均可用，上传控件、状态、错误与空状态不能互相遮挡。

## Open Questions

- None。解析预览明确为无持久化测试接口；默认使用现有 bootstrap owner 凭据进行本地联调。

## Next Actions

1. 修复 parser 重构遗留的失效 import，并运行 parser 聚焦测试。
2. 新增无持久化 parse-preview API 与后端测试。
3. 实现 `/documents` 解析预览页与 API 客户端方法。
4. 使用 Docker Compose 构建并部署，进行真实 parser、桌面与移动端浏览器验证。
