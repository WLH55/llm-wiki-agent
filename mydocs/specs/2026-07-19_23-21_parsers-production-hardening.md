# SDD Spec: parsers 生产化加固（Production Hardening）

## RIPER 状态

- **phase**: RESEARCH
- **approval status**: 无（首版 bootstrap，待用户回答 Open Questions）
- **execute status**: 未开始
- **review status**: 未开始
- **spec path**: `mydocs/specs/2026-07-19_23-21_parsers-production-hardening.md`
- **active project**: llm_wiki3.0（单项目）
- **change scope**: local（backend parsers + document upload/worker 接入层）
- **predecessor**: `mydocs/specs/2026-07-15_16-29_parsers-module.md`（学习版，FINAL PASS）
- **codemap**: `mydocs/codemap/2026-07-19_23-21_parsers-production功能.md`
- **next**: 用户确认 §0 Open Questions → 进入 Innovate/Plan

---

## §0 Open Questions

> 未决前不进入 Execute。带 **[推荐]** 的为默认建议，可用“全部按推荐”一键确认。

- [ ] **Q1：生产化范围？**
  - A. 仅解析内核 hardening（错误契约、资源限制、dispatch 完整返回、worker 正确消费）
  - B. A + 核心格式能力补齐（PDF/DOCX 等）
  - C. **[推荐]** B + 产品接入（上传可选 engine、图片入 MinIO、状态/元数据可观测）
  - D. 全格式生产级（含 OCR、LibreOffice、旧 Office 全转换）——范围过大，不建议第一期

- [ ] **Q2：第一期必达格式？**
  - A. **[推荐]** 核心集：`txt/md/markdown/pdf/docx/xlsx/csv/pptx`
  - B. 核心集 + `html/htm/mhtml/epub/png/jpg/...`
  - C. 注册表已有全部格式均生产级
  - 说明：非必达格式可保留实现，但产品默认拒绝或标记 `experimental`

- [ ] **Q3：图片策略？**
  - A. **[推荐]** 解析后上传 MinIO，正文替换为稳定 object key/URL；DB/metadata 记录图片清单
  - B. 第一期丢弃图片，只保证文本可靠
  - C. 继续 base64 塞进链路（不推荐，膨胀且难缓存）

- [ ] **Q4：PDF 扫描件？**
  - A. **[推荐]** 检测扫描件 → 稳定错误码/告警（不做 OCR）
  - B. 内置 OCR
  - C. 仅当用户选 markitdown/opendataloader 时尝试增强

- [ ] **Q5：旧格式 `.doc` / `.ppt`？**
  - A. **[推荐]** 产品正面拒绝（API 预校验 400 + 明确错误码）
  - B. 容器安装转换工具降级支持
  - C. 静默失败（禁止）

- [ ] **Q6：错误与状态语义？**
  - A. **[推荐]**
    - 解析失败 / 不支持 / 超限 → `failed` + 稳定 `error_code`
    - 合法但无文本（如扫描 PDF、纯图）→ `failed` 或 `processed` + `warning_code=empty_content`（需二选一，推荐 **failed + empty_content**，避免脏向量）
    - 成功 → `processed`，可附 `warnings[]`
  - B. 空文本也 `processed`（保持现状，不推荐）

- [ ] **Q7：未知扩展名？**
  - A. **[推荐]** 上传阶段直接拒绝（白名单）
  - B. 解析阶段拒绝
  - C. 继续 TextParser 兜底（禁止用于生产）

- [ ] **Q8：engine 选择入口？**
  - A. **[推荐]** 上传 API 可选 `parser_engine`；默认 `builtin`；不可用时 400/明确失败
  - B. 仅服务端配置默认引擎，用户不可选
  - C. 第一期不暴露 engine

- [ ] **Q9：是否允许改 DB schema？**
  - A. **[推荐]** 允许增量字段：`parser_engine`、`parse_error_code`、`parse_metadata(jsonb)`（或等价）
  - B. 不改表，只写 `error_message` 文本
  - C. 另建 parse_runs 表

- [ ] **Q10：执行节奏？**
  - A. **[推荐]** 分 Stage 推进：P0 契约/护栏 → P1 图片与核心格式 → P2 观测与测试加固
  - B. 单 PR 一次做完（风险高）

---

## §1 Requirements (Context)

### Goal

将 `backend/app/parsers` 从**学习驱动的可运行实现**升级为**可承受生产流量与脏输入的文档解析子系统**，并打通上传 → 解析 → 分块/嵌入链路中的结果契约、错误语义、资源护栏与（可选）图片持久化。

**非目标重申**：不是重写解析架构，而是在现有 BaseParser / Registry / Chain 上做生产级收口。

### In-Scope（第一期草案，最终以 Q1-Q10 为准）

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
   - 上传或派发前拒绝未知/实验性类型（依 Q2/Q7）
5. **去掉危险兜底**
   - 删除“未知类型 → TextParser”的生产路径

#### P1 产品接入与核心质量（推荐纳入第一期）

1. 上传可选 `parser_engine`，Document 记录实际使用引擎
2. 图片上传 MinIO + 正文路径替换 + 元数据留存
3. 核心格式生产行为：
   - PDF：扫描件检测 + 明确失败/告警；评估是否抽取简单表格
   - DOCX：补图片抽取；表格输出可被 MarkdownTableFormatter 消费
   - XLSX/CSV/PPTX/MD/TXT：补齐超时/输出上限/错误码
4. API/状态查询可返回 `error_code` / warnings / engine

#### P2 可运维（可第二期）

1. 结构化日志与基础指标（耗时、页数、引擎、错误码计数）
2. 恶意/超大/损坏样本测试集
3. 清理教学向注释与 Stage 叙事，改为产品约束文档

### Out-of-Scope（第一期明确不做）

- ❌ gRPC / 独立解析服务拆分
- ❌ MinerU 集成
- ❌ 全量 OCR 平台化（除非 Q4=B）
- ❌ LibreOffice 通用转换中心（除非 Q5=B）
- ❌ 存储多后端（仍 MinIO）
- ❌ 重做 chunker / embedding 算法
- ❌ 前端大改（最多后续接 engine 下拉）
- ❌ 多租户配额与计费

### 验收标准（草案）

1. 任意支持格式解析失败时，文档状态为 `failed`，且存在**稳定 error_code**（不是仅自由文本）。
2. 未知扩展名无法进入成功解析路径（上传拒绝或解析拒绝，依 Q7）。
3. `dispatch` 调用方可获得 `content + images + metadata + error_code`；worker 不再 `parse_to_text → str` 丢信息。
4. 若 Q3=A：含图 Markdown/DOCX/PPTX/EPUB 解析后，图片对象存在于 MinIO，正文引用可定位。
5. 若 Q8=A：上传可指定 engine；不可用引擎返回明确错误；默认 builtin 行为回归通过。
6. 核心格式集在样本集上：
   - happy path 全过
   - 超大/超时/损坏文件有护栏
   - 不出现“失败却 processed”的状态污染
7. 现有 parser 单测回归不下降；新增生产契约测试（错误码、白名单、dispatch 结构、worker 状态机）。
8. 学习版 Spec 的架构决策（无 chunks 字段、Registry 双 key、Markdown Pipeline）保持兼容，不无故推翻。

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
- **Open Questions**: 见 §0 Q1-Q10

---

## §2 Research Findings

### 事实与约束

1. **学习版目标已完成**：parsers 模块、双 key Registry、Chain/Pipeline、多格式 parser、基础单测（130 passed / 1 skipped）均已落地。
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
| 图片持久化增加 MinIO 成本与权限面 | 运维 | Q3 可选；key 租户隔离 |
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

1. **等待用户回答 §0 Q1-Q10**（可回复“全部按推荐”）。
2. 确认后进入 **Innovate（短）+ Plan**：
   - 冻结第一期范围与状态矩阵
   - 给出 File Changes / Signatures / 原子 Checklist（建议 Stage P0/P1/P2）
3. 用户精确回复 `Plan Approved` 后才允许 Execute。
4. **禁止事项**：当前 phase=RESEARCH，不得修改业务代码。

---

## §3 Innovate (Optional)

> 待 Open Questions 关闭后补全。预研备选方向如下，供决策参考。

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

- **Selected**: 待用户确认 Q1-Q10
- **Why**: 生产化范围与图片/OCR/旧格式策略会显著改变 Plan 文件集

---

## §4 Plan (Contract)

> 未锁定 Open Questions 前，Plan 仅放**骨架**，防止未批准细节被当成可执行合同。

### §4.1 File Changes（预估，待确认后冻结）

**P0 可能改动**

- `backend/app/parsers/dispatch.py` — 结构化结果；去 Text 兜底
- `backend/app/parsers/base.py` / 新建 `errors.py` / `limits.py` — 错误码与限制
- `backend/app/parsers/document.py` — 必要时扩展 metadata 约定（非 chunks）
- `backend/app/workers/parse_document.py` — 消费完整结果与状态矩阵
- `backend/app/services/document_service.py` / `routers/document.py` / `schemas/document.py` — 白名单、engine、错误码 API
- `backend/app/models/document.py` + alembic — 可选字段
- `backend/tests/test_parsers/test_dispatch*.py` + worker 契约测试

**P1 可能改动**

- `minio_service.py` + 图片回写辅助
- `pdf_parser.py` / `docx2_parser.py` / 相关测试
- markdown/pptx/epub 图片路径与存储对接

### §4.2 Signatures

- TBD after Q1-Q10

### §4.3 Implementation Checklist

- [ ] 关闭 Open Questions
- [ ] 冻结状态矩阵与错误码表
- [ ] 写 P0 Plan 原子步骤
- [ ] `Plan Approved`
- [ ] Execute P0 → Review
- [ ] Execute P1 → Review
- [ ]（可选）P2

### §4.4 Spec Review Notes

- 当前阶段仅 RESEARCH 首版，不进行 `review_spec` GO/NO-GO 判定。
- Plan 可执行性：PARTIAL（骨架已有，签名未冻结）

---

## §5 Execute Log

- 未开始（No Approval, No Execute）

---

## §6 Review Verdict

- 未开始

---

## §7 Plan-Execution Diff

- 无

---

## §8 Archive Record

- 待本 Spec 闭环后再 archive
- predecessor 学习版 Spec 可在主题归档中作为 “teaching baseline” 引用

---

## 热上下文快照（每轮聚焦）

| 项 | 值 |
|----|----|
| phase | RESEARCH |
| approval | 无 |
| Goal | parsers 生产化加固 |
| In-Scope | 契约/错误/护栏/（推荐）图片与核心格式/engine 接入 |
| Out-of-Scope | gRPC、MinerU、全面 OCR、多存储后端 |
| Active Checklist | 回答 Q1-Q10 |
| Next Action | 用户确认 Open Questions |
| 风险 | 范围膨胀；状态语义回归；图片与超時代价 |
