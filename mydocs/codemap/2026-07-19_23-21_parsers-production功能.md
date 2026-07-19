# CodeMap: parsers 生产化（feature）

- **生成时间**: 2026-07-19_23-21
- **mode**: feature
- **goal**: 将学习版 `backend/app/parsers` 升级为可承受生产负载的文档解析链路
- **scope**: `backend/app/parsers/**` + `backend/app/workers/parse_document.py` + `backend/app/services/document_service.py` + `backend/app/routers/document.py` + `backend/app/models/document.py` + `backend/app/services/minio_service.py`

---

## 1. Entry Points

| 入口 | 路径 | 作用 |
|------|------|------|
| 上传 API | `backend/app/routers/document.py` → `upload_document_endpoint` | 接收文件，触发异步解析 |
| 上传服务 | `backend/app/services/document_service.py` → `upload_document` | 50MB 校验、MinIO 存原文件、写 DB、入队 |
| Worker | `backend/app/workers/parse_document.py` → `parse_document_task` | 拉文件 → 解析 → 分块 → 嵌入 → 写 chunks |
| 派发 | `backend/app/parsers/dispatch.py` → `parse_to_text` | 按扩展名/engine 选 parser，**当前只返回 content** |
| Registry | `backend/app/parsers/registry.py` → `ParserEngineRegistry` | `(engine, file_type)` 双 key + builtin fallback |
| 模块装载 | `backend/app/parsers/__init__.py` → `_register_defaults` | 注册 builtin / markitdown / opendataloader |

## 2. Core Flow

```text
UploadFile
  → document_service.upload_document
      → minio.upload_bytes(original)
      → DB documents(status=pending)
      → queue.enqueue_parse_document
  → parse_document_task
      → minio.get_bytes
      → dispatch.parse_to_text(filename, bytes)   # 丢失 images/metadata/error
      → chunker.chunk_text
      → embed_texts
      → INSERT content_chunks
      → status=processed|failed
```

## 3. Parser 能力分层（现状）

### 3.1 接近生产

- `web_fetcher.py`: SSRF 校验、请求拦截、超时、HTML 体积上限
- `epub_parser.py`: ZIP bomb / 成员数 / 压缩比防护
- `csv_parser.py` / `excel_parser.py`: 行列/单元格上限
- `image_parser.py`: 像素上限
- `registry.py`: 双 key、原子注册、availability probe 隔离
- `markdown_parser.py`: 表格标准化 + base64 抽取管道

### 3.2 教学简化（生产缺口）

- `pdf_parser.py`: 仅文字层 extract_text；无表格/扫描检测/OCR/layout
- `docx2_parser.py`: 无图片、无标题层级；表格粗拼接
- `doc_parser.py`: 依赖本机 antiword/catdoc；失败变空 content
- `ppt_convert.py`: 拒旧 `.ppt`；无资源上限
- `dispatch.py`: 只返回 str；未知扩展名兜底 TextParser
- `image_parser.py`: `ocr_status=not_configured`
- worker: 不消费 images/metadata；空文本也可 processed

### 3.3 已实现但未接通产品

- `markitdown_parser.py` / `opendataloader_parser.py`
- Registry engine 列表
- `Document.images` 契约

## 4. Data Contracts

| 契约 | 位置 | 说明 |
|------|------|------|
| Parser 输出 | `parsers/document.py` | `content + images + metadata`（无 chunks） |
| DB Document | `models/document.py` | 无 `parser_engine` / `parse_metadata` / 图片引用字段 |
| API schema | `schemas/document.py` | 仅 status/filename/error_message |
| 对象存储 | `services/minio_service.py` | 仅原文件 upload/get；无图片派生对象约定 |

## 5. Dependencies

- 解析库：pdfplumber / python-docx / openpyxl / xlrd / python-pptx / ebooklib / Pillow / playwright / trafilatura
- 可选引擎：markitdown / opendataloader-pdf(+Java)
- 外部命令：antiword/catdoc（.doc）
- 基础设施：Postgres / Redis queue / MinIO / Embedding API

## 6. Risk Hotspots

1. **契约断层**：parser 三元组 → worker 只吃 content
2. **错误语义分裂**：异常 vs `metadata.error` vs 空文本 processed
3. **资源无统一预算**：缺全局 max_bytes / parse timeout / 输出长度
4. **未知类型兜底文本化**：脏数据入库
5. **图片无持久化**：解析出的 images 随进程丢弃
6. **engine 无产品入口**：高级引擎无法被调用方选择

## 7. Suggested Change Surfaces（供新 Spec）

| 优先级 | 表面 | 原因 |
|--------|------|------|
| P0 | `dispatch.py` / `parse_document.py` / `document.py(parser)` | 完整结果与错误契约 |
| P0 | `document_service.py` / `routers/document.py` / DB model | 拒未知类型、可选 engine、状态语义 |
| P0 | 统一 limits + 错误码 | 生产护栏 |
| P1 | MinIO 图片回写 + markdown 路径替换 | 图文不丢 |
| P1 | PDF/DOCX 能力补强 | 核心格式质量 |
| P2 | 观测指标 / 恶意样本测试 | 可运维 |
