# SDD Spec: parsers 生产化加固（Production Hardening）

## RIPER 状态

- **phase**: REVIEW
- **approval status**: `Plan Approved`（2026-07-20）
- **execute status**: 已完成
- **review status**: PASS（三轴审查完成）
- **spec path**: `mydocs/specs/2026-07-19_23-21_parsers-production-hardening.md`
- **active project**: llm_wiki3.0（单项目）
- **change scope**: local（backend parsers + document upload/worker 接入层）
- **predecessor**: `mydocs/specs/2026-07-15_16-29_parsers-module.md`（学习版，FINAL PASS）
- **codemap**: `mydocs/codemap/2026-07-19_23-21_parsers-production功能.md`
- **execution mode**: 用户已要求审批后自动批量执行、Review、commit、push
- **next**: Review PASS 后执行 commit + push

---

## §0 Open Questions

> 2026-07-20 方案完善时按原 Spec 推荐项收敛。产品决策已经关闭；`Plan Approved` 是唯一剩余执行门禁。

- [x] **Q1：生产化范围？**
  - A. 仅解析内核 hardening（错误契约、资源限制、dispatch 完整返回、worker 正确消费）
  - B. A + 核心格式能力补齐（PDF/DOCX 等）
  - C. **[推荐]** B + 产品接入（上传可选 engine、图片入 MinIO、状态/元数据可观测）
  - D. 全格式生产级（含 OCR、LibreOffice、旧 Office 全转换）——范围过大，不建议第一期

- [x] **Q2：第一期必达格式？**
  - A. **[推荐]** 核心集：`txt/md/markdown/pdf/docx/xlsx/csv/pptx`
  - B. 核心集 + `html/htm/mhtml/epub/png/jpg/...`
  - C. 注册表已有全部格式均生产级
  - 说明：非必达格式可保留实现，但产品默认拒绝或标记 `experimental`

- [x] **Q3：图片策略？**
  - A. **[推荐]** 解析后上传 MinIO，正文替换为稳定 object key/URL；DB/metadata 记录图片清单
  - B. 第一期丢弃图片，只保证文本可靠
  - C. 继续 base64 塞进链路（不推荐，膨胀且难缓存）

- [x] **Q4：PDF 扫描件？**
  - A. **[推荐]** 检测扫描件 → 稳定错误码/告警（不做 OCR）
  - B. 内置 OCR
  - C. 仅当用户选 markitdown/opendataloader 时尝试增强

- [x] **Q5：旧格式 `.doc` / `.ppt`？**
  - A. **[推荐]** 产品正面拒绝（API 预校验 400 + 明确错误码）
  - B. 容器安装转换工具降级支持
  - C. 静默失败（禁止）

- [x] **Q6：错误与状态语义？**
  - A. **[推荐]**
    - 解析失败 / 不支持 / 超限 → `failed` + 稳定 `error_code`
    - 合法但无文本（如扫描 PDF、纯图）→ `failed` 或 `processed` + `warning_code=empty_content`（需二选一，推荐 **failed + empty_content**，避免脏向量）
    - 成功 → `processed`，可附 `warnings[]`
  - B. 空文本也 `processed`（保持现状，不推荐）

- [x] **Q7：未知扩展名？**
  - A. **[推荐]** 上传阶段直接拒绝（白名单）
  - B. 解析阶段拒绝
  - C. 继续 TextParser 兜底（禁止用于生产）

- [x] **Q8：engine 选择入口？**
  - A. **[推荐]** 上传 API 可选 `parser_engine`；默认 `builtin`；不可用时 400/明确失败
  - B. 仅服务端配置默认引擎，用户不可选
  - C. 第一期不暴露 engine

- [x] **Q9：是否允许改 DB schema？**
  - A. **[推荐]** 允许增量字段：`parser_engine`、`parse_error_code`、`parse_metadata(jsonb)`（或等价）
  - B. 不改表，只写 `error_message` 文本
  - C. 另建 parse_runs 表

- [x] **Q10：执行节奏？**
  - A. **[推荐]** 分 Stage 推进：P0 契约/护栏 → P1 图片与核心格式 → P2 观测与测试加固
  - B. 单 PR 一次做完（风险高）

### §0.1 冻结决策

| 决策面 | 冻结结论 |
|---|---|
| 第一期范围 | Q1=C：P0 内核 + P1 核心格式/图片/产品接入；P2 观测指标另期 |
| 生产上传白名单 | `txt/md/markdown/pdf/docx/xlsx/csv/pptx`；其他现有 parser 保留但视为 experimental |
| 图片 | Markdown/DOCX/PPTX 解析图片写 MinIO；正文改写为稳定 `minio://<bucket>/<key>` 引用；DB metadata 记清单 |
| PDF 扫描件 | 只检测，不做 OCR；无文本层时 `failed + empty_content` |
| 旧 Office | `.doc/.ppt` 在上传阶段 400，错误语义为 `unsupported_type` |
| 空内容 | `failed + empty_content`，禁止生成空向量或标记 `processed` |
| engine | 上传表单可选，默认 `builtin`；未知、不可用或不支持该格式均 400，显式选择不得静默回退 |
| DB | 新增可空/有默认值字段 `parser_engine/parse_error_code/parse_metadata`，兼容旧行 |
| 节奏 | P0 → P1 顺序执行；用户已要求批量完成，但执行仍受 `Plan Approved` 硬门禁约束 |

---

## §1 Requirements (Context)

### Goal

将 `backend/app/parsers` 从**学习驱动的可运行实现**升级为**可承受生产流量与脏输入的文档解析子系统**，并打通上传 → 解析 → 分块/嵌入链路中的结果契约、错误语义、资源护栏与图片持久化。

**非目标重申**：不是重写解析架构，而是在现有 BaseParser / Registry / Chain 上做生产级收口。

### In-Scope（第一期冻结范围）

#### P0 内核 hardening（必做）

1. **完整解析结果契约**
   - `dispatch` 返回结构化结果（至少 `content/images/metadata/error_code`），不再只返回 `str`
   - worker 按契约决策 success/failed，不再吞掉 `metadata.error`
2. **统一错误模型**
   - 稳定错误码：`unsupported_type` / `parse_failed` / `timeout` / `too_large` / `empty_content` / `engine_unavailable` / `unsafe_url` 等
   - parser 失败语义统一（推荐：可恢复信息进 metadata，不可解析必须可被 worker 识别为 failed）
3. **输入/资源护栏**
   - 全局：`max_file_bytes`、`parse_timeout_seconds`、`max_output_chars`
   - 复用并统一各 parser 已有局部限制（CSV/Excel/EPUB/Image/Web）
4. **扩展名白名单**
   - 上传阶段只允许 `txt/md/markdown/pdf/docx/xlsx/csv/pptx`
   - dispatch 对任何未注册类型返回 `unsupported_type`，不允许成功兜底
5. **去掉危险兜底**
   - 删除“未知类型 → TextParser”的生产路径

#### P1 产品接入与核心质量（本期必做）

1. 上传可选 `parser_engine`，Document 记录请求且实际使用的引擎；显式 engine 不允许静默 fallback
2. Markdown/DOCX/PPTX 图片上传 MinIO + 正文 `minio://` 路径替换 + 元数据留存
3. 核心格式生产行为：
   - PDF：基于页数/文本页数检测扫描件并明确失败；本期不新增表格抽取
   - DOCX：补图片抽取；表格输出可被 MarkdownTableFormatter 消费
   - XLSX/CSV/PPTX/MD/TXT：补齐超时/输出上限/错误码
4. API/状态查询可返回 `error_code` / warnings / engine

#### P2 可运维（明确延期，不在本次 Execute）

1. 结构化日志与基础指标（耗时、页数、引擎、错误码计数）
2. 恶意/超大/损坏样本测试集
3. 清理教学向注释与 Stage 叙事，改为产品约束文档

### Out-of-Scope（第一期明确不做）

- ❌ gRPC / 独立解析服务拆分
- ❌ MinerU 集成
- ❌ 全量 OCR 平台化
- ❌ LibreOffice 通用转换中心
- ❌ 存储多后端（仍 MinIO）
- ❌ 重做 chunker / embedding 算法
- ❌ 前端大改（最多后续接 engine 下拉）
- ❌ 多租户配额与计费

### 验收标准（冻结）

1. 任意支持格式解析失败时，文档状态为 `failed`，且存在**稳定 error_code**（不是仅自由文本）。
2. 白名单外扩展名在上传阶段返回 HTTP 400，响应 `data.error_code=unsupported_type`；直接调用 dispatch 时得到同名错误码，两条路径均不能进入成功解析。
3. `dispatch.parse_document` 返回 `ParseResult(content, images, metadata, engine, error_code, warnings)`；worker 不再通过 `parse_to_text → str` 丢信息。
4. 含图 Markdown/DOCX/PPTX 解析后，图片对象存在于 MinIO，正文使用 `minio://<bucket>/<key>`，`parse_metadata.images` 可追踪对象 key、来源路径与 content type。
5. 上传可指定 engine；未知/不可用/不支持格式的 engine 返回 HTTP 400 与 `data.error_code=engine_unavailable`；默认 builtin 回归通过；显式 engine 绝不静默 fallback。
6. 核心格式集在样本集上：
   - happy path 全过
   - 超大/超时/输出过大/损坏文件有护栏并产生稳定错误码
   - 不出现“失败却 processed”的状态污染
7. 现有 parser 单测回归不下降；新增生产契约测试（错误码、白名单、dispatch 结构、worker 状态机）。
8. 学习版 Spec 的架构决策（无 chunks 字段、Registry 双 key、Markdown Pipeline）保持兼容，不无故推翻。
9. Alembic `002` 可正向新增字段且可独立 downgrade；旧数据读取时使用默认 `builtin`、空 error code、空 metadata。
10. `python -m pytest tests/test_parsers -q` 与本次新增 worker/service 单测全部通过；`ruff check` 对本次变更文件零错误且不增加全仓基线错误。需要外部 Postgres/Redis/MinIO 的集成测试若环境不可用，必须明确记录而不得伪造通过。

---

## §1.1 Context Sources

- **Requirement Source**
  - 用户口述（2026-07-19）：“需要将当时为了教学考量的部分改为可以承受生产级的产品”
  - 用户指令（2026-07-19）：`/sdd-riper-one 出新的spec`
- **Predecessor Spec**
  - `mydocs/specs/2026-07-15_16-29_parsers-module.md`（Stage 1-11 FINAL PASS）
- **Design / Code Refs**
  - `mydocs/codemap/2026-07-19_23-21_parsers-production功能.md`
  - `backend/app/parsers/**`
  - `backend/app/workers/parse_document.py`
  - `backend/app/services/document_service.py`
  - `backend/app/routers/document.py`
  - `backend/app/models/document.py`
  - `backend/app/services/minio_service.py`
- **Prior Analysis**
  - 会话内生产缺口分析：契约断层、错误语义、资源护栏、图片丢失、engine 未接通、PDF/DOCX 教学简化

---

## §1.5 Codemap Used

- **Codemap Mode**: feature
- **Codemap File**: `mydocs/codemap/2026-07-19_23-21_parsers-production功能.md`
- **Key Index**
  - Entry: upload API → document_service → queue → parse_document_task → dispatch → registry → parser
  - 断层点: `dispatch.parse_to_text` 只返回 content；worker 忽略 images/metadata
  - 已有护栏: Web SSRF、EPUB zip、CSV/Excel 维度、Image 像素
  - 未接通: engine 选择、图片持久化、统一错误码

---

## §1.6 Context Bundle Snapshot

- **Bundle Level**: Lite（由会话分析直接沉淀，未另建 bundle 文件）
- **Key Facts**
  1. 学习版架构可复用，不必重写 Registry/BaseParser
  2. 生产最大漏洞在“接入契约”而非“有没有 parser 文件”
  3. 上传已有 50MB 限制，但 parser/worker 缺统一超时与错误码
  4. Document 表无 engine/metadata 字段，产品可观测性不足
- **Open Questions**: None（Q1-Q10 已按 §0.1 冻结）

---

## §2 Research Findings

### 事实与约束

1. **学习版目标已完成**：parsers 模块、双 key Registry、Chain/Pipeline、多格式 parser 均已落地；2026-07-20 基线 `python -m pytest tests/test_parsers -q` 为 **131 passed / 0 failed**。
   - 全量 pytest 基线：**133 passed / 13 setup errors**；13 项均因 `POSTGRES_DSN` 为空、外部数据库环境未配置。
   - 全仓 Ruff 基线：**113 errors（94 auto-fixable）**，分布在既有代码；本任务禁止借机全仓格式化，只要求触及文件零错误且不增加基线。
2. **产品主链只消费文本**：
   - `dispatch.parse_to_text(... ) -> str`
   - `parse_document_task` 用字符串分块嵌入
   - 导致 images/metadata/error 全丢
3. **失败常被软化**：
   - 多数 parser `return Document(content="", metadata={error: ...})`
   - worker 对空文本走 `processed + error="无文本内容"`，污染状态语义
4. **未知类型危险兜底**：dispatch 对未注册扩展名使用 TextParser。
5. **局部护栏存在但不统一**：CSV/Excel/EPUB/Image/Web 各自为政；PDF/DOCX/PPTX/DOC 缺少同类预算。
6. **高级引擎已实现未产品化**：Registry 可挂 markitdown/opendataloader，但 API/DB/worker 无 engine 参数贯通。
7. **MinIO 仅存原文件**：具备 `upload_bytes/get_bytes`，缺“解析派生图片”的 key 约定与回写流程。
8. **DB Document 字段偏瘦**：`status/error_message/original_filename/minio_key`，无 engine/error_code/parse_metadata。

### 根因判断

> 不是“解析器太少”，而是 **教学期刻意简化的边界** 直接留在了 **生产主链**：
> 1) 结果契约被压成 string；2) 错误被当成空文本；3) 护栏未全局化；4) 图片与 engine 没有产品落点。

### 风险与不确定项

| 风险 | 影响 | 缓解 |
|------|------|------|
| 范围膨胀到 OCR/LibreOffice/全格式 | 长期做不完 | Q1/Q2 锁第一期最小集 |
| 改 worker 状态语义导致前端/测试假设变化 | 回归 | 明确 status 矩阵 + 更新测试 |
| 图片持久化增加 MinIO 成本与权限面 | 运维 | 总量限制；key 按知识库/文档隔离；不生成公开 URL |
| PDF 表格/扫描检测准确率 | 误报/漏报 | 先做保守检测 + 错误码，不做完美 layout |
| 统一超时在同步 parser 中难精确抢占 | 长尾任务 | 先文档/队列 job_timeout + parser 内部协作式检查，再考虑进程级隔离 |
| DB 迁移与在线兼容 | 发布风险 | 只加可空字段，读路径兼容旧行 |

### 与旧 Spec 的关系

| 旧决策 | 生产化态度 |
|--------|------------|
| Document 无 chunks | **保持**（分块仍在 chunker） |
| 不做 gRPC | **保持** |
| Registry 双 key | **保持并接通产品** |
| Markdown Pipeline | **保持并接图片存储** |
| 学习向 Stage 叙事 | **替换为产品约束** |
| 未知类型 Text 兜底 | **废除** |
| 空文本 processed | **废除（默认）** |

---

## §2.1 Next Actions

1. 按 §4.3 直接批量实现全部 P0/P1 checklist，完成后统一补齐和运行测试。
2. 执行三轴 `review_execute`；任何 FAIL 回到 Plan 修正，全部 PASS 后才 commit/push。
3. 验证时区分纯单元测试与依赖外部基础设施的集成测试，并保留真实证据。

---

## §3 Innovate (Optional)

> Open Questions 已关闭；以下备选与最终选择作为决策记录保留。

### 决策面 A：结果契约怎么改

| 方案 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| A1 | `ParseResult` 数据类，dispatch 返回对象 | 清晰、可扩展 | 要改 worker/测试 |
| A2 | 继续返回 `parsers.Document`，另用异常表达失败 | 复用现有模型 | 错误码/警告表达弱 |
| A3 | **[推荐倾向]** `ParseResult(document, error_code, warnings, engine, stats)` | 成功失败同一返回型，worker 好简单 | 多一个薄封装 |

### 决策面 B：图片怎么落

| 方案 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| B1 | **[推荐倾向]** MinIO key: `{kb}/{doc_id}/images/{name}` + 替换正文 | 可引用、可清理 | 要实现存储与回滚 |
| B2 | 第一期丢弃 images | 最快 | 图文产品能力缺失 |
| B3 | DB jsonb 存 base64 | 实现快 | 库膨胀，不可取 |

### 决策面 C：格式能力补齐深度

| 方案 | 做法 | 优点 | 缺点 |
|------|------|------|------|
| C1 | **[推荐倾向]** 核心格式“可靠失败 + 基本质量”，不追求版面完美 | 可交付 | 扫描 PDF/复杂 layout 仍弱 |
| C2 | 核心格式尽量接近 docreader 全能力 | 质量高 | 工期长、依赖重 |
| C3 | 全部交给外部 engine | 少维护 | 默认路径能力空心化 |

### Decision

- **Selected**: A3 + B1 + C1
- **Why**: `ParseResult` 在不推翻现有 parser `Document` 契约的前提下补齐边界语义；MinIO 稳定引用避免 base64 进入 DB/向量；核心格式优先保证可靠成功/失败，不在本期追求 OCR/layout 完美。
- **Rejected**: 继续 string 契约、DB 存 base64、全量 OCR/LibreOffice、外部 engine 全面替代 builtin。

---

## §4 Plan (Contract)

### §4.0 行为合同

#### 状态矩阵

| 场景 | status | parse_error_code | processed_at | 后续分块/嵌入 |
|---|---|---|---|---|
| 解析成功且有文本 | `processed` | `NULL` | 当前 UTC | 是 |
| 未知/实验性扩展名 | 上传 400；dispatch 失败结果 | `unsupported_type` | `NULL` | 否 |
| 显式 engine 未知/不可用/不支持格式 | 上传 400；worker 防御性失败 | `engine_unavailable` | `NULL` | 否 |
| parser 报错或返回 legacy `metadata.error` | `failed` | 映射后的稳定码，默认 `parse_failed` | `NULL` | 否 |
| 合法输入但无文本（含扫描 PDF） | `failed` | `empty_content` | `NULL` | 否 |
| 文件/输出/图片总量超限 | `failed` | `too_large` | `NULL` | 否 |
| parser 超时 | `failed` | `timeout` | `NULL` | 否 |
| 成功但存在非阻断问题 | `processed` | `NULL`，问题写 `warnings[]` | 当前 UTC | 是 |

#### 错误码表

稳定值限定为：`unsupported_type`、`parse_failed`、`timeout`、`too_large`、`empty_content`、`engine_unavailable`、`unsafe_url`。自由文本仅进入 `error_message`/metadata，不得充当机器判断字段。

#### 资源预算

| 配置 | 默认值 | 执行点 |
|---|---:|---|
| `PARSER_MAX_FILE_BYTES` | 50 MiB | upload + dispatch 双重校验 |
| `PARSER_MAX_OUTPUT_CHARS` | 5,000,000 | dispatch 返回前校验，超限失败而非静默截断 |
| `PARSER_MAX_TOTAL_IMAGE_BYTES` | 20 MiB | 图片解码/上传前累计校验 |
| `PARSER_TIMEOUT_SECONDS` | 300 s | worker 通过 `asyncio.wait_for(asyncio.to_thread(...))` 包裹同步 parser |
| `PARSER_JOB_TIMEOUT_SECONDS` | 600 s | RQ 外层兜底，必须大于 parser timeout |

#### API/DB 持久化合同

- 上传校验失败统一返回 HTTP 400，沿用 `ApiResponse` 外壳，并在 `data.error_code` 放稳定字符串码；文件超限=`too_large`，类型不支持=`unsupported_type`，engine 问题=`engine_unavailable`。
- `documents.parser_engine`: `VARCHAR(50) NOT NULL DEFAULT 'builtin'`。
- `documents.parse_error_code`: `VARCHAR(50) NULL`。
- `documents.parse_metadata`: `JSONB NOT NULL DEFAULT '{}'::jsonb`，包含 parser 原始 metadata、`warnings` 与持久化后的 `images` 清单，禁止存 base64。
- 迁移 `upgrade` 只新增字段；`downgrade` 仅按相反顺序删除这三个字段，不触碰旧列或数据。

### §4.1 File Changes

**P0：契约、护栏、状态与产品入口**

- `backend/app/parsers/result.py`（新建）— `ParseErrorCode`、`ParseLimits`、`ParseResult` 与 legacy metadata 错误映射。
- `backend/app/parsers/dispatch.py` — 新增结构化 `parse_document`；保留 `parse_to_text` 仅作兼容薄层；删除未知类型 TextParser 兜底。
- `backend/app/parsers/registry.py` — 增加 engine/格式严格查询与 availability 查询；兼容调用仍可显式选择是否 builtin fallback。
- `backend/app/parsers/__init__.py` — 导出新契约，修正未知类型说明。
- `backend/app/config/settings.py` — 增加四项 parser 预算和 RQ timeout 配置。
- `backend/app/config/exceptions.py` — `BusinessValidationException` 支持稳定字符串 `error_code`，400 响应写入 `data.error_code`。
- `backend/app/models/document.py` — 增加 `parser_engine`、`parse_error_code`、`parse_metadata`。
- `backend/alembic/versions/002_parser_hardening.py`（新建）— 可逆增量迁移，字段均兼容旧行。
- `backend/alembic.ini` — 将配置注释改为 ASCII，避免 Windows locale 读取 UTF-8 中文注释时阻塞 Alembic CLI。
- `backend/app/schemas/document.py` — 上传/状态响应暴露 engine、error code、metadata/warnings。
- `backend/app/routers/document.py` — multipart `parser_engine` 表单参数，默认 `builtin`。
- `backend/app/main.py` — 请求日志中间件跳过 multipart body 缓存，避免在上传校验前无界读入文件。
- `backend/app/services/document_service.py` — 上传白名单、engine availability/support 预校验、字段写入与状态返回。
- `backend/app/services/minio_service.py` — MinIO SDK 改为 client 首次使用时懒加载，使不触及存储的校验/状态单测不依赖外部 SDK。
- `backend/app/workers/queue.py` — RQ timeout 改由设置提供。
- `backend/app/workers/parse_document.py` — 超时包装、完整结果消费、确定性状态矩阵、解析元数据持久化。
- `backend/tests/test_parsers/test_parse_document_dispatch.py` — 结构化结果、严格 engine、错误映射和预算测试。
- `backend/tests/test_parser_hardening_service.py`（新建）— 上传白名单/engine 校验/响应契约单测。
- `backend/tests/test_parse_document_worker.py`（新建）— success/empty/error/timeout 状态机单测。
- `backend/tests/test_parser_migration.py`（新建）— 验证 `002` upgrade 列类型/默认值与 downgrade 逆序删除合同。

**P1：图片与核心格式质量**

- `backend/app/services/parser_asset_service.py`（新建）— 安全规范化图片名、base64 解码、总量限制、MinIO 上传和正文路径替换。
- `backend/app/parsers/docx2_parser.py` — 提取 DOCX media，追加稳定 Markdown 图片引用并返回 base64 images。
- `backend/app/parsers/pdf_parser.py` — 写入 `text_page_count/empty_page_count/is_scanned`，扫描件由 dispatch 统一转 `empty_content`。
- `backend/app/workers/parse_document.py` — 在分块前持久化图片，将对象清单写入 `parse_metadata.images`。
- `backend/tests/test_parser_asset_service.py`（新建）— 路径穿越、重复名、非法 base64、总量限制、正文替换与 MinIO 调用测试。
- `backend/tests/test_parsers/test_docx_parser.py` — DOCX 图片提取与正文引用测试。
- `backend/tests/test_parsers/test_pdf_parser.py` — 扫描件标记与 partial empty pages 测试。
- `backend/tests/test_parsers/test_ppt_parser.py` / `test_markdown_parser.py` — 既有图片契约回归。

**不改动**：前端、chunker/embedding 算法、experimental parser 能力、独立解析服务、OCR/LibreOffice、P2 指标平台。

### §4.2 Signatures

```python
class ParseErrorCode(str, Enum): ...

class ParseDispatchError(RuntimeError):
    error_code: ParseErrorCode

@dataclass(frozen=True)
class ParseLimits:
    max_file_bytes: int
    max_output_chars: int
    max_total_image_bytes: int

class ParseResult(BaseModel):
    content: str
    images: dict[str, str]
    metadata: dict[str, Any]
    engine: str
    error_code: ParseErrorCode | None
    warnings: list[str]

def parse_document(
    filename: str,
    raw_bytes: bytes,
    engine: str = BUILTIN_ENGINE,
    limits: ParseLimits | None = None,
) -> ParseResult: ...

def parse_to_text(filename: str, raw_bytes: bytes, engine: str | None = None) -> str: ...

def get_parser_class(
    engine_or_file_type: str,
    file_type: str | None = None,
    *,
    fallback_to_builtin: bool = True,
) -> type[BaseParser]: ...

def get_engine_status(engine: str) -> dict[str, object] | None: ...

class BusinessValidationException(Exception):
    def __init__(
        self,
        message: str,
        code: int | None = None,
        error_code: str | None = None,
    ) -> None: ...

async def upload_document(
    db: AsyncSession,
    kb_id: int,
    user: User,
    filename: str,
    content: bytes,
    content_type: str,
    parser_engine: str = BUILTIN_ENGINE,
) -> DocumentUploadResponse: ...

# upload_document_endpoint 内部读取上限
content = await file.read(settings.PARSER_MAX_FILE_BYTES + 1)

def persist_parser_images(
    kb_id: int,
    doc_id: UUID,
    content: str,
    images: Mapping[str, str],
    max_total_bytes: int,
) -> tuple[str, list[dict[str, Any]]]: ...

async def _mark_status(
    db: AsyncSession,
    doc: Document,
    status: str,
    *,
    error_message: str = "",
    error_code: str | None = None,
    parse_metadata: dict[str, Any] | None = None,
) -> None: ...
```

约束：`parse_to_text` 只为旧内部/测试调用兼容，不得被生产 worker 使用；若结构化结果失败则抛出 `ParseDispatchError`，不能返回可被误判成功的文本。对象 key 固定为 `{kb_id}/{doc_id}/images/{sha256-prefix}-{safe-basename}`，同一输入可幂等覆盖；正文存储 `minio://{bucket}/{key}`，不生成短期 presigned URL。

### §4.3 Implementation Checklist

- [x] 1. 关闭 Q1-Q10，冻结范围、状态矩阵、错误码和资源预算。
- [x] 2. 运行基线 parser 单测并记录 `131 passed`。
- [x] 3. 获得精确口令 `Plan Approved`（2026-07-20）。
- [x] 4. 实现 `result.py`、dispatch 与 registry 的结构化结果、严格 engine、错误映射与预算控制。
- [x] 5. 实现配置、API error payload、service/schema/model/Alembic/queue/worker 状态机。
- [x] 6. 补齐并运行 P0 dispatch/API/service/worker 测试。
- [x] 7. P0 测试全绿且无范围外改动。
- [x] 8. **P0 Review**：迁移兼容、显式 engine 无 fallback、失败路径不分块均通过。
- [x] 9. 实现安全 MinIO 图片持久化和 worker 接入。
- [x] 10. 实现 DOCX 图片提取与 PDF 扫描标记。
- [x] 11. 补齐并运行图片服务、DOCX/PDF 及 Markdown/PPTX 回归测试。
- [x] 12. 运行 parser/service/worker/migration 测试、可用的全量 pytest、触及文件 Ruff。
- [x] 13. 执行三轴 `review_execute`；发现并修复 DOCX 非连续 GFM 表格问题后重审 PASS。
- [x] 14. 回写 Execute Log、Review Matrix、Plan-Execution Diff 和验证证据。
- [ ] 15. 仅在 Review PASS 且工作区只含本任务改动时 commit；随后 push 当前 `llm_wiki3.0` 分支到 `origin`。

### §4.4 Spec Review Notes

| Check | Verdict | Evidence |
|---|---|---|
| Goal / scope / acceptance | PASS | §0.1、§1 的第一期边界和 10 条可验证验收标准已冻结 |
| Plan executability | PASS | §4.1 给出精确文件，§4.2 给出签名，§4.3 为原子执行 checklist |
| State/error contract | PASS | §4.0 明确成功、空内容、超限、超时、engine 与 legacy error 语义 |
| Risk / rollback readiness | PASS | 新字段向后兼容且迁移可逆；experimental parser/前端/P2 均不扩入本期 |
| Test strategy | PASS | 已有 131 passed 基线；按用户决策不采用 TDD，完成实现后统一补齐 parser/worker/service 测试并执行 Ruff 验证 |

- **Readiness Verdict**: GO（建议性结论）
- **Risks & Suggestions**: `asyncio.to_thread` 超时不能强杀底层线程，属于当前单进程架构的已知折中；RQ 600s 外层超时兜底。本期不宣称具备进程级资源隔离。
- **Phase Reminders**: Execute 后必须补全 §5；Review 必须三轴审查并补全 §6/§7；外部基础设施不可用的集成测试需如实记录。
- **Execution Gate**: `Plan Approved` 已收到，允许按 batch override 进入 Execute。

---

## §5 Execute Log

- 2026-07-20：收到精确 `Plan Approved`，phase 切换为 EXECUTE。
- 2026-07-20：用户明确要求不使用 TDD 和 subagent-driven-development；执行方式调整为直接批量实现后统一测试与审查。
- 2026-07-20：实现自审发现上传路由与请求日志中间件会在 service 校验前无界读取 multipart；先回写 Plan，再增加 multipart 跳过缓存与 `max+1` 有界读取。
- 2026-07-20：真实 Alembic 1.18 离线执行发现 `alembic.ini` 的 UTF-8 中文注释在 Windows GBK locale 下触发 `UnicodeDecodeError`；先回写 Plan，再改为 ASCII 注释。
- Pre-execute baseline：parser tests `131 passed`；全量 pytest `133 passed + 13 setup errors`（缺 `POSTGRES_DSN`）；全仓 Ruff 113 个历史错误。
- P0：完成 `ParseResult/ParseErrorCode/ParseLimits`、严格 engine、错误映射、文件/输出/图片预算、机器可读 API 400、DB 模型与 `002` 迁移、worker 状态机和超时处理。
- P1：完成内容寻址的 MinIO 图片持久化、Markdown 路径改写、DOCX 图片/GFM 表格、PDF 扫描标记和 multipart 有界读取。
- Review fix：DOCX 表格最初按 `\n\n` 分隔各行，不构成合法 GFM；审查中改为单一 `\n` 连续表格块并加强测试。
- Validation：
  - parser + service + asset + worker + migration：`162 passed`。
  - 全量 pytest（最近一次）：`157 passed + 13 setup errors`；13 项与执行前相同，均因 `POSTGRES_DSN` 为空，未进入测试主体。
  - 触及文件 `ruff check`：PASS。
  - FastAPI OpenAPI：multipart 暴露必填 binary `file` 和默认 `builtin` 的可选 `parser_engine`。
  - Alembic 1.18 PostgreSQL offline upgrade：PASS，生成 `001 -> 002` 三条 ADD COLUMN。
  - Alembic offline downgrade `002:001`：PASS，逆序 DROP 三列。

---

## §6 Review Verdict

| Axis | Key Checks | Verdict | Evidence |
|---|---|---|---|
| Spec Quality & Requirement Completion | Goal/In-Scope/10 条验收、状态矩阵、资源预算、延期项 | PASS | §0.1/§1/§4.0；162 项目标测试、OpenAPI、迁移 SQL |
| Spec-Code Fidelity | §4.1 文件、§4.2 签名、§4.3 checklist、错误/状态/图片行为 | PASS | `git diff` 逐项核对；Reverse Sync 偏差均记录于 §7 |
| Code Intrinsic Quality | 正确性、输入安全、超时、路径安全、迁移回滚、测试、lint | PASS | 162 passed；Ruff PASS；upgrade/downgrade PASS；审查修复 GFM 问题 |

- **Overall Verdict**: PASS
- **Blocking Issues**: None
- **Regression Risk**: Medium（修改上传/DB/worker 主链；单元与离线迁移证据充分，但本机无真实 PostgreSQL/Redis/MinIO 集成环境）
- **Residual Risks**:
  1. `asyncio.to_thread` 超时无法强杀底层解析线程，RQ 600s 仅作进程级外层兜底。
  2. MinIO 网络中断可能留下已按确定性 key 上传的部分对象；重试会幂等覆盖，本期未实现对象事务/清理任务。
  3. 扫描 PDF 仅检测并失败，不含 OCR；符合本期范围。
- **Follow-ups**: P2 增加真实基础设施集成测试、进程级解析隔离、指标与孤立派生对象清理。

---

## §7 Plan-Execution Diff

- **User-directed**：批准后用户明确取消 TDD 与 subagent-driven-development；改为直接实现、统一测试与本地三轴审查。
- **Reverse Sync - upload memory guard**：增加 `app/main.py` multipart body 日志跳过和路由 `max+1` 有界读取，修复 service 校验前无界加载。
- **Reverse Sync - Windows Alembic**：增加 `alembic.ini` ASCII 注释修复，消除 Alembic 1.18 在 GBK locale 的配置读取错误。
- **Testability**：MinIO SDK、queue 和 DB session factory 改为边界懒加载；实际调用语义不变，允许不依赖外部 SDK/DSN 的单元测试导入。
- **Validation addition**：新增 migration 契约测试，并实际验证 Alembic upgrade/downgrade 离线 SQL。
- **Unauthorized deviation**: None

---

## §8 Archive Record

- **Skipped**: 本次不生成额外 archive 派生文档；活动 Spec 已包含完整决策、执行、验证与 Review 证据。
- predecessor 学习版 Spec 保留，可在后续主题归档中作为 “teaching baseline” 引用。

---

## 热上下文快照（每轮聚焦）

| 项 | 值 |
|----|----|
| phase | REVIEW |
| approval | `Plan Approved` |
| Goal | parsers 生产化加固 |
| In-Scope | P0 契约/错误/护栏/API/DB + P1 核心格式/MinIO 图片/engine 接入 |
| Out-of-Scope | experimental 上传、P2 指标、前端、gRPC、MinerU、OCR、LibreOffice、多存储后端 |
| Active Checklist | §4.3 Step 15：commit + push |
| Next Action | 工作区最终审计后提交并推送 `llm_wiki3.0` |
| 风险 | `to_thread` 超时非进程级强杀；DB 迁移；状态语义回归；图片限额与路径安全 |
