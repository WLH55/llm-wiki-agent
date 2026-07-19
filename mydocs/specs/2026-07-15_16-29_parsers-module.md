# SDD Spec: backend/app/parsers 文档解析模块（参考 docreader 移植）

## RIPER 状态

- **phase**: REVIEW（FINAL PASS）
- **approval status**: Gate 8-11 批量推进授权（用户指令“接下来把所有阶段都完成”，2026-07-19）；最终三轴 Review PASS
- **execute status**: Stage 1 ✅ / Stage 2 ✅ / Stage 3 ✅ / Stage 4 ✅ / Stage 5 ✅ / Stage 6 ✅ / Stage 7 ✅ / Stage 8 ✅ / Stage 9 ✅ / Stage 10 ✅ / Stage 11 ✅
- **review status**: FINAL PASS（Stage 9-11 三轴 Review，2026-07-19）
- **spec path**: `mydocs/specs/2026-07-15_16-29_parsers-module.md`
- **active project**: llm_wiki3.0（单项目）
- **change scope**: local（`backend/app/parsers/` + `backend/app/workers/parse_document.py` + `backend/tests/test_parsers/`）
- **current stage**: COMPLETE（全部 11 个 Stage 完成）
- **current step**: Step 20 已完成并通过最终 Review
- **next**: 可选 `archive` 沉淀；无未完成 checklist

---

## §0 Open Questions

> 学习驱动的开发任务。2026-07-15 用户分两轮回答了所有问题。

- [x] **Q1：Document 模型要不要带 `chunks` 字段？** → **A（去掉）**
  - 决策：Document 只保留 `content + images + metadata` 三字段
  - 理由：现有 `workers/chunker.py` 独立分块，Document 不背分块产物

- [x] **Q2：Registry 第一次实现就上双 key 还是先单层？** → **B（先单层，后升）**
  - 决策：先单 key（按 file_type 派发）跑通架构；PDF 多引擎需求出现时再升双 key
  - 理由：把"注册表模式"和"多引擎维度"两个概念分开讲

- [x] **Q3：ChainParser 什么时候做？** → **C（MarkdownParser 升级时）**
  - 决策：ChainParser 在 MarkdownParser 升级为 `PipelineParser(TableFormatter, ImageBase64Extractor)` 时一起做
  - 理由：组合模式只有具体场景才能讲清楚价值

- [x] **Q4：测试策略？** → **B（每 parser 一个 happy-path 单测）**
  - 决策：`backend/tests/test_parsers/` 下每 parser 一个 test 文件
  - 理由：学习阶段不追求覆盖率，聚焦契约正确性

- [x] **Q5：旧 `workers/parsers.py` 何时删？** → **A（接入完成后立刻删）**
  - 决策：接入 backend 完成后同 PR 内删除
  - 理由：保留两套代码 = 永远清不掉的 tech debt

- [x] **Q6：复刻范围多大？**（2026-07-15 用户第二轮明确）→ **A（完美复刻 17 个 parser）**
  - 决策：移植 docreader/parser/ 下全部 17 个 parser
  - 理由：用户明确"完美复刻各种文档处理能力"

- [x] **Q7：parser 之外的辅助能力？**（2026-07-15）→ **图片抽取 + 表格格式化 + utils（endecode）**
  - 决策：移植 `MarkdownImageUtil` + `MarkdownTableUtil` + `docreader/utils/endecode.py`
  - 不要：splitter（结构感知分块，现有 `workers/chunker.py` 够用）

- [x] **Q8：高级引擎（MarkitDown / OpenDataLoader）的外部依赖怎么处理？**（2026-07-19）→ **按需安装，但实现完整适配器**
  - `MarkitdownParser` 需微软 `markitdown`；`OpenDataLoaderParser` 需 `opendataloader-pdf` + Java 11+
  - 两者放入 `advanced` 可选依赖组，默认 `pip install .` 不安装；需要时使用 `pip install ".[advanced]"`
  - Parser 模块只做惰性 import，未安装时仍可导入整个 `app.parsers`，解析时返回 `metadata.error`
  - Stage 7 不加入默认单 key Registry；Stage 8 升级双 key 后再注册为可选 engine

- [x] **Q9：Excel 非 XLSX 格式是否在默认上传路径自动调用 LibreOffice？**（2026-07-18）→ **否**
  - 决策：默认上传路径和 parser 模块均不启动 LibreOffice
  - 决策：删除 `find_soffice()` / `convert_excel_to_xlsx_bytes()` 外部转换能力
  - 理由：学习项目无需引入外部进程、安装差异和沙箱问题
  - 来源：Step 10 WIP 测试与实现冲突；用户指令“ok 你来”授权按推荐方案收口

- [x] **Q10：表格文件支持范围？**（2026-07-18）→ **`.xlsx/.xls/.csv`**
  - `.xlsx`：`ExcelParser` + `openpyxl`，支持多 Sheet、合并单元格
  - `.xls`：独立 `XlsParser` + `xlrd`，直接读取旧版二进制格式，不经 LibreOffice
  - `.csv`：独立 `CsvParser` + Python `csv` 标准库，支持编码识别与分隔符嗅探
  - `.xlsb/.ods/.et`：明确不支持，Registry 不注册
  - 来源：用户确认“这种表格只支持 xlsx、xls、csv”并回复“好的”

- [x] **Q11：PPT 支持范围与代码注释语言？**（2026-07-18）
  - 格式范围：只支持现代 `.pptx`；旧 `.ppt` 不调用 LibreOffice，不注册
  - 文本：`PptxParser` 使用 python-pptx 按幻灯片和 shape 顺序提取文本
  - 媒体：提取 `ppt/media/` 下文件，输出为 `Document.images` 的 Base64 映射，并在正文附媒体路径
  - 语言：后续新增或修改的代码注释、模块说明和 docstring 统一使用中文
  - 来源：用户指令“现在进入下一个阶段”“代码注释用中文比较好”

- [x] **Q12：URL 网页由谁抓取？**（2026-07-18 用户决策）→ **Stage 5 提供 URL → Document 能力，Fetcher 与 Parser 内部分层**
  - 用户明确要求复用 docreader 的网页抓取能力，覆盖普通网页文章和微信公众号文章
  - `WebParser` 对外接受 URL bytes；内部调用独立 `web_fetcher.py` 获取渲染后的 HTML/可见文本/标题
  - `WebFetcher` 使用同步 Playwright Chromium，兼容当前同步 `BaseParser.parse()`；不照搬会在现有事件循环中失败的 `asyncio.run()`
  - `WebParser` 使用 Trafilatura 提取正文，并复用 docreader 的微信公众号 `#js_content/.rich_media_content/mmbiz.qpic.cn` 适配
  - 分层理由：抓取负责网络安全、超时、重试和增量同步；Parser 保持确定性的 bytes → Document 契约
  - `MHTMLParser` 解析 `.mhtml/.mht` MIME 归档，提取主 HTML 与内嵌图片
  - 两者复用同一个 HTML → Markdown 函数，避免转换规则分叉
  - URL 原始 HTML 保存到 MinIO、创建数据库 Document 和增量同步仍由后续 `WebUrlSourceAdapter` 接入；当前 Stage 5 先完成 URL → Document
  - 来源：用户明确提出“复用他的能力，我也要可以抓取微信公众号文章、网页文章”

---

## §1 Requirements (Context)

### Goal

**完美复刻** docreader/parser/ 模块的文档解析能力到 `backend/app/parsers/`，作为 Python in-process 模块（不做 gRPC、不做独立服务）。**学习驱动**：边搭边讲，让用户深入理解每个抽象的设计动机和模式应用。

**学习目标（用户能口述）**：
1. 为什么 if-elif 撑不住未来扩展（开闭原则）
2. 抽象基类如何定义接口契约（abc.ABC + abstractmethod + 模板方法）
3. 注册表模式如何替代字典查找（双 key 派发 + 能力列举）
4. 责任链 / 管道组合模式如何复用 parser（FirstParser / PipelineParser）
5. 17 种文档格式各自的解析技术要点（PDF 表格 / Word 段落 / Excel 多 sheet / PPT 媒体 / 网页 HTML / 邮件 MHTML / 电子书 EPUB / 图片元数据 等）
6. Markdown 表格标准化 + Base64 图片抽取的实现细节

### In-Scope（必做）

#### A. 核心抽象（4 个文件）

| 文件 | 来源 | 学习重点 |
|------|------|---------|
| `parsers/document.py` | `docreader/models/document.py`（裁剪：去 chunks） | Pydantic 契约设计 |
| `parsers/base.py` | `docreader/parser/base_parser.py` | abc.ABC + 模板方法 |
| `parsers/registry.py` | `docreader/parser/registry.py` | 注册表模式（单 key → 双 key） |
| `parsers/chain.py` | `docreader/parser/chain_parser.py` | 责任链 + 管道 |

#### B. Utils 辅助（1 个文件）

| 文件 | 来源 | 学习重点 |
|------|------|---------|
| `parsers/_utils/endecode.py` | `docreader/utils/endecode.py` | 编码检测 + bytes/str 转换（几乎所有 parser 依赖） |

#### C. 17 个 Parser（按格式族分组）

| 格式族 | 文件 | 来源 | 外部依赖 |
|--------|------|------|---------|
| 文本 | `text_parser.py`（新写） | - | 无 |
| Markdown | `markdown_parser.py` | docreader 原版 | 无（含表格/图片 utils） |
| Word | `docx2_parser.py` / `doc_parser.py` | docreader 原版 | python-docx / unstructured / catdoc |
| PDF | `pdf_parser.py` | docreader 原版 | pdfplumber |
| 表格套件 | `excel_parser.py` + `xls_parser.py` + `csv_parser.py` + `excel_convert.py` + `xlsx_merge.py` + `xlsx_repair.py` | docreader 裁剪 + 新写 | openpyxl / xlrd / 标准库 csv |
| PPT 套件 | `ppt_convert.py` + `pptx_media.py` | docreader 原版 | python-pptx |
| 网页 | `web_fetcher.py` + `web_parser.py` | docreader 裁剪 | playwright + trafilatura + lxml |
| 邮件 | `mhtml_parser.py` | docreader 裁剪 | 标准库 email + HTML 转换依赖 |
| 电子书 | `epub_parser.py` | docreader 原版 | ebooklib |
| 图片 | `image_parser.py` | docreader 原版 | Pillow |
| 高级引擎 | `markitdown_parser.py` / `opendataloader_parser.py` | docreader 原版 | markitdown / opendataloader-pdf + Java |

#### D. 测试

| 文件 | 覆盖 |
|------|------|
| `tests/test_parsers/test_*.py` | 每 parser 一个 happy-path 单测 |

### Out-of-Scope（明确不做）

- ❌ **gRPC 服务化**（`proto/` / `main.py` / `auth.py`）：同语言无需 RPC（用户决策 2026-07-15）
- ❌ **独立容器部署**：作为 backend 内 Python 模块
- ❌ **Go client SDK**（`client/`）：无跨语言需求
- ❌ **MinerU 集成**：作为外部 endpoint，留 P4
- ❌ **并发限流**（`concurrency.py`）：单 worker 串行就够
- ❌ **存储多后端**（COS/OSS 配置）：MinIO 单一选择
- ❌ **TLS/Auth**：内网同进程调用，无网络边界
- ❌ **Splitter**（结构感知分块）：现有 `workers/chunker.py` 够用（用户决策 2026-07-15）
- ❌ **Document.chunks 字段**：分块独立在 chunker，Document 不背
- ❌ **`.xlsb/.ods/.et` 表格格式**：本学习任务只覆盖 `.xlsx/.xls/.csv`
- ❌ **LibreOffice 自动转换**：不启动外部 Office 进程；三种格式均使用 Python 库原生解析
- ❌ **Stage 5 内完成 URL 持久化 API/SourceAdapter**：本阶段完成 URL → Document；MinIO/DB/增量同步另立 Spec 接入

### 验收标准

1. `backend/app/parsers/` 目录建好，含 4 核心抽象 + 1 utils + parser 模块 = **~24 个文件**
2. `backend/app/workers/parsers.py` **已删除**
3. `backend/app/workers/parse_document.py` 改为 `from app.parsers import registry`
4. `tests/test_parsers/` 下每 parser 一个 happy-path 测试，全部通过
5. 已有的 `tests/test_document.py` 回归测试仍通过
6. 用户能口述清楚：BaseParser / Registry / ChainParser 三大抽象的设计动机
7. 用户能独立加一个新 parser（如 HTMLParser）而不改 Registry 代码（开闭原则验证）
8. 用户能口述各类格式的解析技术要点，并能区分 XLSX/旧版 XLS/CSV 的存储结构

---

## §1.1 Context Sources

- **Requirement Source**：
  - 用户口述（2026-07-15）：参考 docreader 模块**完美复刻**所有文档处理能力，分步骤学习
  - 用户决策 1（2026-07-15）：只要文档解析部分，其他不要；不做 gRPC；同语言无需独立部署
  - 用户决策 2（2026-07-15）：全部 17 parser；图片抽取 + 表格格式化 + endecode utils；Document 裁剪版去 chunks
  - `mydocs/parser-design-pattern.md`（设计模式教学文档）
- **Design Refs**：
  - `docreader/parser/` 全部 17 个文件
  - `docreader/parser/base_parser.py` / `registry.py` / `chain_parser.py`（核心抽象源）
  - `docreader/parser/markdown_parser.py`（PipelineParser 实战 + 表格 + 图片 utils）
  - `docreader/models/document.py`（Document 数据契约源，将裁剪）
  - `docreader/utils/endecode.py`（编码处理源）
- **Existing Code**：
  - `backend/app/workers/parsers.py`（60 行 if-elif 占位，将被替换）
  - `backend/app/workers/parse_document.py`（消费 parsers 的入口）
  - `backend/app/workers/chunker.py`（分块逻辑，不动）

---

## §1.1 Context Sources

- **Requirement Source**：
  - 用户口述（2026-07-15）：参考 docreader 模块实现自己的文档解析模块，分步骤学习
  - 用户决策（2026-07-15）：只要文档解析部分，其他不要；不做 gRPC；同语言无需独立部署
  - `mydocs/parser-design-pattern.md`（设计模式教学文档）
- **Design Refs**：
  - `docreader/parser/base_parser.py`（BaseParser 抽象基类源）
  - `docreader/parser/registry.py`（ParserEngineRegistry 源）
  - `docreader/parser/chain_parser.py`（FirstParser + PipelineParser 源）
  - `docreader/parser/markdown_parser.py`（PipelineParser 实战示例）
  - `docreader/models/document.py`（Document 数据契约源）
- **Existing Code**：
  - `backend/app/workers/parsers.py`（60 行 if-elif 占位，将被替换）
  - `backend/app/workers/parse_document.py`（消费 parsers 的入口）
  - `backend/app/workers/chunker.py`（分块逻辑，不动）
- **Chat/Business Refs**：
  - 用户 grilling 全程（2026-07-15）：从"看 MVP 模块"到"docreader 该作为 Python 库接入"

---

## §1.5 Codemap Used

- **Codemap Mode**：N/A（学习型任务，直接读 docreader/ 源码即可，无需生成 codemap）
- **Key Index**：
  - `docreader/parser/` 17 个文件，已读核心 5 个（base / registry / chain / markdown / document）
  - `backend/app/workers/parsers.py` 占位代码
  - `mydocs/parser-design-pattern.md` 设计模式教学文档

---

## §1.6 Context Bundle Snapshot

- **Bundle Level**：N/A（直接复用 docreader/ 源码 + 设计模式文档）
- **Key Facts**：docreader 已是完整参考实现，本项目只需裁剪 + 教学化重构
- **Open Questions**：见 §0

---

## §2 Research Findings

### 事实与约束

1. **docreader/parser/ 的设计核心是 4 个抽象**：
   - **Document**（数据契约）：`content: str + images: Dict + metadata: Dict`
   - **BaseParser**（接口契约）：`parse_into_text(content: bytes) -> Document`（抽象）+ `parse(content)`（模板方法）
   - **ParserEngineRegistry**（注册表）：按 `(engine, file_type)` 双 key 派发，builtin engine 兜底
   - **ChainParser**（组合）：FirstParser（责任链 try A 失败 try B）+ PipelineParser（管道 A 输出喂给 B）

2. **当前 `workers/parsers.py` 的 3 个硬伤**（已通过 grilling 第 8 问分析）：
   - 加格式必须改核心函数体（违反开闭原则）
   - 同格式多引擎无法共存（单维 key 表达不了双维需求）
   - 无法运行时列举能力（硬编码 SUPPORTED_FORMATS 双份维护）

3. **docreader/parser/ 的 17 个 parser 中，本项目 MVP 范围只需 4 个**：
   - PDF（`pdf_parser.py`，使用 pdfplumber）
   - DOCX（`docx2_parser.py`，使用 python-docx 或 unstructured）
   - Markdown（`markdown_parser.py`，但先写最简版）
   - TXT（无对应文件，新写 TextParser）

4. **接入入口**：`workers/parse_document.py` 第 ~70 行调用 `parse_by_filename`，改为 `registry.get_parser(file_type).parse(content)` 即可

5. **测试基线**：`backend/tests/test_document.py` 已覆盖"上传 MD → status=processed"，是回归基线

### 设计模式对照

| 经典模式 | docreader 中的角色 | 解决的问题 |
|---------|-------------------|----------|
| **策略模式** | BaseParser + 各具体 parser | 同一接口多种实现可互换 |
| **模板方法** | BaseParser.parse()（非抽象）调 parse_into_text()（抽象） | 公共流程（日志）放基类，可变部分（实际解析）放子类 |
| **注册表模式** | ParserEngineRegistry | 替代全局字典，封装 + 提供列举能力 |
| **责任链** | FirstParser | try A 失败 try B，第一个成功的赢 |
| **管道** | PipelineParser | A 输出喂给 B，串行流水线 |
| **工厂方法** | FirstParser.create() / PipelineParser.create() | 动态生成子类，避免每次手动继承 |

### 风险与不确定项

1. **【低风险】学习曲线 vs 工程进度的平衡**
   - 8 步走完需要数小时教学时间
   - 缓解：每步独立验证，可暂停可恢复；spec 持久化进度

2. **【低风险】docreader 原版代码依赖外部 utils**
   - `docreader/parser/markdown_parser.py` 依赖 `docreader.utils.endecode`
   - 缓解：本项目新写最简 MarkdownParser，不直接搬运 markdown_parser.py

3. **【低风险】PdfParser / DocxParser 搬运时 import 路径调整**
   - docreader 内部 import 用 `from docreader.parser.base_parser import BaseParser`
   - 本项目改为 `from app.parsers.base import BaseParser`
   - 缓解：Step 4 / Step 7 搬运时统一改 import 路径

4. **【无风险】向后兼容**
   - 旧 `workers/parsers.py` 的 `parse_by_filename(filename, data) -> str` 与新 API 不一致（新 API 返回 Document）
   - 缓解：`parse_document.py` 调用方一并改；外部无其他调用方

### 关键教学验证点

1. **学习者能口述**：BaseParser 为什么是 ABC + abstractmethod
2. **学习者能口述**：Registry 为什么不能是全局可变字典
3. **学习者能独立加 HTMLParser**：不改 Registry 代码（开闭原则验证）
4. **学习者能区分**：FirstParser 和 PipelineParser 何时用哪个

### Stage 8 Research Findings（2026-07-19）

1. **现状是单 key Registry**：`backend/app/parsers/registry.py` 只有 `file_type -> parser class`，无法表达同一 PDF 同时由 builtin、MarkItDown、OpenDataLoader 解析。
2. **现有调用仍依赖单参数查询**：`backend/app/workers/parse_document.py` 和多个格式测试均调用 `registry.get_parser_class(file_type)`；Step 20 才计划让 worker 接收显式 engine。
3. **兼容边界**：Stage 8 新增双参数 `get_parser_class(engine, file_type)`，同时保留单参数形式并将其解释为 builtin 查询，避免提前修改 worker 或批量改动格式测试。
4. **异常契约必须稳定**：现有 worker 捕获 `KeyError` 后回退 `TextParser`，因此 builtin 也不支持的格式继续抛 `KeyError`，不改为参考实现中的 `ValueError`。
5. **高级引擎已具备可用性探针**：`markitdown_available()` 与 `opendataloader_available()` 均为零参数函数，可直接供 `list_engines()` 生成 `available / unavailable_reason` 元数据。
6. **注册范围**：builtin 保持当前全部格式；markitdown 注册 `md/markdown/pdf/docx/doc/pptx/ppt/xlsx/xls/csv`；opendataloader 只注册 `pdf`。
7. **影响面**：本阶段只修改 `registry.py`、`parsers/__init__.py`、`test_registry.py`；不修改 worker、API、数据库或 parser 实现。

---

## §2.1 Next Actions

> §0 Open Questions 已全部决策（Q1-Q13 完成；Q8 已在 Stage 7 确认为按需安装），进入 Plan 阶段。

1. **【当前】Stage 8 Plan 已完成**：精确文件、签名、兼容规则和原子 checklist 见 §4。
2. **等待用户精确回复 `Plan Approved`**。
3. **批准后进入 Execute**：按 15.1-15.5 实施并统一验证。
4. **Execute 完成后进入 Stage 8 Review**：三轴评审通过后停在 Gate 8。

---

## §3 Innovate (Optional: Options & Decision)

> 2026-07-15 Plan 阶段补充。docreader 是既定参考，无大方案对比，仅 3 个小决策。

### 决策 1：Registry 简化版 vs 直接双 key

- **Selected**：**先单 key（按 file_type），后升级双 key**
- **Why**：把"注册表模式"和"多引擎维度"两个概念分开教学，避免一次塞两个新概念
- **Avoided**：直接上双 key（一次性引入 `Dict[engine, Dict[file_type, parser_cls]]` 嵌套字典，认知负担过重）

### 决策 2：MarkdownParser 分阶段实现

- **Selected**：**3 阶段递进**
  - 阶段 7：最简版（仅 decode → Document）
  - 阶段 16-17：加表格 utils + 图片 utils（独立类）
  - 阶段 19：升级为 `PipelineParser(TableFormatter, ImageBase64)`
- **Why**：让用户看到 PipelineParser 的价值——单 parser 长得太胖，拆成阶段后用组合模式串起来
- **Avoided**：一步到位写完整 MarkdownParser（用户看不到为什么要用 PipelineParser）

### 决策 3：高级引擎（MarkitDown / OpenDataLoader）的依赖处理

- **Selected**：**完整实现适配器，但依赖放入 `advanced` 可选依赖组**
- **Why**：Stage 7 已完成惰性加载、可用性检查和完整转换路径；默认安装仍不引入重依赖。
- **Avoided**：直接跳过这两个（违背"完美复刻"原则）

### Stage 8 Innovate 结论

- **Skipped + Reason**：双 key Registry 是既定架构，参考实现与当前调用链均已明确；本阶段只需解决兼容迁移，不存在需要用户选择的竞争方案。

---

## §4 Plan (Contract)

### §4.1 File Changes（项目结构）

```
backend/app/parsers/                      # 新增模块
├── __init__.py                           # 导出 Document / BaseParser / registry
├── document.py                           # 数据契约（Pydantic，去 chunks）
├── base.py                               # BaseParser 抽象基类
├── registry.py                           # ParserRegistry（单 key → 双 key 升级）
├── chain.py                              # FirstParser + PipelineParser（Step 18）
│
├── _utils/                               # 内部工具
│   └── endecode.py                       # 编码处理（移植自 docreader/utils/）
│
├── text_parser.py                        # TextParser（最简，新写）
├── markdown_parser.py                    # MarkdownParser（3 阶段递进）
├── docx2_parser.py                       # Word .docx
├── doc_parser.py                         # Word 老式 .doc
├── pdf_parser.py                         # PDF（pdfplumber）
├── excel_parser.py                       # XLSX（openpyxl）
├── xls_parser.py                         # 旧版 XLS（xlrd）
├── csv_parser.py                         # CSV（标准库 csv）
├── excel_convert.py                      # 表格格式识别；不执行外部转换
├── xlsx_merge.py                         # Excel 辅助：多 sheet 合并
├── xlsx_repair.py                        # Excel 辅助：损坏文件修复
├── ppt_convert.py                        # PptxParser：幻灯片文本提取（不做旧 PPT 转换）
├── pptx_media.py                         # PPTX 媒体文件抽取
├── web_fetcher.py                        # Playwright URL 抓取与 URL 安全校验
├── web_parser.py                         # Trafilatura 正文提取与微信文章适配
├── mhtml_parser.py                       # MHTML 邮件存档
├── epub_parser.py                        # EPUB 电子书
├── image_parser.py                       # 图片元数据（Pillow）
├── markitdown_parser.py                  # MarkItDown 引擎（微软库）
└── opendataloader_parser.py              # OpenDataLoader 引擎（Java）

backend/app/workers/
├── parsers.py                            # ❌ 删除（Step 6）
└── parse_document.py                     # ✏ 改：from app.parsers import registry

backend/tests/test_parsers/               # 新增测试目录
├── __init__.py
├── test_document.py
├── test_base.py
├── test_registry.py
├── test_chain.py
├── test_text_parser.py
├── test_markdown_parser.py
├── test_docx_parser.py
├── test_doc_parser.py
├── test_pdf_parser.py
├── test_excel_parser.py
├── test_xls_parser.py
├── test_csv_parser.py
├── test_ppt_parser.py
├── test_web_parser.py
├── test_mhtml_parser.py
├── test_epub_parser.py
├── test_image_parser.py
├── test_markitdown_parser.py             # skip if 依赖未装
└── test_opendataloader_parser.py         # skip if 依赖未装
```

**总计**：~24 个 parser 模块文件 + 18 个测试文件

### §4.2 Signatures（核心签名）

#### Document（数据契约）

```python
# backend/app/parsers/document.py
from pydantic import BaseModel, Field
from typing import Any, Dict

class Document(BaseModel):
    """parser 输出契约：content + images + metadata（无 chunks）"""
    content: str = Field(default="", description="解析后的 markdown 文本")
    images: Dict[str, str] = Field(default_factory=dict, description="图片路径 → base64")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="文档元数据")

    def is_valid(self) -> bool:
        return self.content != ""
```

#### BaseParser（抽象基类）

```python
# backend/app/parsers/base.py
from abc import ABC, abstractmethod

class BaseParser(ABC):
    """所有 parser 的抽象基类（模板方法 + 策略模式）"""

    def __init__(self, file_name: str = "", file_type: str | None = None, **kwargs):
        self.file_name = file_name
        self.file_type = file_type or os.path.splitext(file_name)[1].lstrip(".")

    @abstractmethod
    def parse_into_text(self, content: bytes) -> Document:
        """子类必须实现：bytes → Document"""

    def parse(self, content: bytes) -> Document:
        """模板方法：日志 + 调子类实现"""
        logger.info("Parsing with %s, bytes: %d", self.__class__.__name__, len(content))
        document = self.parse_into_text(content)
        logger.info("Extracted %d chars", len(document.content))
        return document
```

#### ParserRegistry（注册表）

```python
# backend/app/parsers/registry.py（简化版 → 双 key 版）

# === 简化版（Step 5） ===
class ParserRegistry:
    def __init__(self):
        self._parsers: Dict[str, Type[BaseParser]] = {}

    def register(self, file_type: str, parser_cls: Type[BaseParser]) -> None: ...
    def get_parser_class(self, file_type: str) -> Type[BaseParser]: ...
    def list_supported(self) -> List[str]: ...

# === 双 key 升级版（Step 15） ===
BUILTIN_ENGINE = "builtin"

class ParserEngineRegistry:
    def __init__(self) -> None:
        self._engines: Dict[str, Dict[str, Type[BaseParser]]] = {}
        self._descriptions: Dict[str, str] = {}
        self._check_available: Dict[str, Callable[[], tuple[bool, str]]] = {}
        self._unavailable_hints: Dict[str, str] = {}

    def register(
        self,
        engine: str,
        file_types: Dict[str, Type[BaseParser]],
        description: str = "",
        check_available: Callable[[], tuple[bool, str]] | None = None,
        unavailable_hint: str = "",
    ) -> None: ...
    def get_parser_class(
        self,
        engine_or_file_type: str,
        file_type: str | None = None,
    ) -> Type[BaseParser]: ...
    def list_supported(self, engine: str = BUILTIN_ENGINE) -> List[str]: ...
    def list_engines(self) -> List[Dict[str, object]]: ...
    def get_engine_names(self) -> List[str]: ...

# 兼容现有导入；新代码优先使用 ParserEngineRegistry。
ParserRegistry = ParserEngineRegistry
```

**Stage 8 行为契约**：

- `register()` 统一把 engine/file_type 规范为去空白、小写且去掉扩展名前导点；先校验整张映射均为 `BaseParser` 子类，再原子替换该 engine，禁止部分注册。
- 规范化后的空 engine、空 file_type 或重复 file_type 均属于配置错误，必须在写入任何状态前抛 `ValueError`，保证失败注册不污染已有 engine。
- `get_parser_class("pdf")` 等价于 `get_parser_class(BUILTIN_ENGINE, "pdf")`，保留当前 worker 与格式测试的调用方式。
- `get_parser_class("markitdown", "pdf")` 命中指定引擎；指定引擎不存在或不支持该格式时回退 builtin。
- 指定引擎与 builtin 均不支持时抛 `KeyError`，错误信息包含请求 engine、file_type 和 builtin 支持列表。
- `list_supported(engine)` 返回该引擎格式的稳定排序列表；未知 engine 返回空列表。
- `list_engines()` 按 engine 名稳定排序，返回 `name / description / file_types / available / unavailable_reason`；可用性探针异常或不符合 `tuple[bool, str]` 的返回值必须被转换为不可用元数据，不能使列表接口失败，且 `available` 始终为真正的 `bool`。
- builtin 永远视为可用；markitdown 与 opendataloader 分别接入现有零参数可用性函数。
- 模块级 `registry` 的运行时类型为 `ParserEngineRegistry`；保留 `ParserRegistry` 别名只用于兼容现有导入。

### §4.2.1 Stage 8 File Changes（精确范围）

| 文件 | 动作 | 目的 |
|---|---|---|
| `backend/app/parsers/registry.py` | 修改 | 实现双 key Registry、builtin fallback、兼容查询与能力列举 |
| `backend/app/parsers/__init__.py` | 修改 | 按 engine 批量注册 builtin、markitdown、opendataloader，并导出 Registry 公共符号 |
| `backend/tests/test_parsers/test_registry.py` | 修改 | 用 TDD 固化双 key、fallback、校验、排序、可用性和兼容契约 |

**明确不改**：`backend/app/workers/parse_document.py` 的显式 engine 传参仍属于 Step 20；现有单参数查询由兼容入口维持。

#### ChainParser（组合模式）

```python
# backend/app/parsers/chain.py
class FirstParser(BaseParser):
    """责任链：try parsers 顺序执行，第一个返回 is_valid() 的赢"""
    _parser_cls: Tuple[Type[BaseParser], ...] = ()

    @classmethod
    def create(cls, *parser_classes) -> Type["FirstParser"]:
        """工厂方法：动态生成配置好的子类"""

class PipelineParser(BaseParser):
    """管道：A 输出 bytes 喂给 B，images/metadata 累加"""
    _parser_cls: Tuple[Type[BaseParser], ...] = ()

    @classmethod
    def create(cls, *parser_classes) -> Type["PipelineParser"]: ...
```

#### 表格 Step 10 契约（2026-07-18 二次修订）

```python
# backend/app/parsers/excel_convert.py
def detect_excel_format(content: bytes) -> str | None: ...
def normalize_excel_bytes(content: bytes, file_type: str | None = None) -> bytes: ...

# backend/app/parsers/xlsx_repair.py
def validate_xlsx_archive(content: bytes) -> None: ...
def repair_xlsx_bytes(content: bytes) -> bytes | None: ...

# backend/app/parsers/excel_parser.py
def _validate_sheet_dimensions(sheet_name: str, max_row: int, max_column: int) -> None: ...

class ExcelParser(BaseParser):
    def parse_into_text(self, content: bytes) -> Document: ...

# backend/app/parsers/xls_parser.py
class XlsParser(BaseParser):
    def parse_into_text(self, content: bytes) -> Document: ...

# backend/app/parsers/csv_parser.py
class CsvParser(BaseParser):
    def parse_into_text(self, content: bytes) -> Document: ...
```

- `normalize_excel_bytes()` 只允许原生 XLSX，不调用外部程序
- `validate_xlsx_archive()` 做学习版最小限制：单成员大小、总解压大小、压缩比
- `_validate_sheet_dimensions()` 用最大单元格数限制 XLSX/XLS 工作表
- `CsvParser` 使用 `decode_bytes()` + `csv.Sniffer`（失败时回退逗号），限制最大行数与列数
- 默认 Registry 注册 `xlsx -> ExcelParser`、`xls -> XlsParser`、`csv -> CsvParser`

#### PPTX Step 11 契约（2026-07-18 补充）

```python
# backend/app/parsers/pptx_media.py
def extract_pptx_media(content: bytes) -> dict[str, str]: ...

# backend/app/parsers/ppt_convert.py
def normalize_pptx_bytes(content: bytes, file_type: str | None = None) -> bytes: ...

class PptxParser(BaseParser):
    def parse_into_text(self, content: bytes) -> Document: ...
```

- `normalize_pptx_bytes()` 只接受有效 PPTX ZIP 包；旧 `.ppt` 或无效输入明确失败
- `extract_pptx_media()` 使用确定性路径 `images/<原文件名>`，值为原始媒体 Base64
- `PptxParser` 输出 `## Slide N` 分节文本；有媒体时追加 `## 媒体` 路径列表
- 默认 Registry 只注册 `pptx -> PptxParser`，不注册 `ppt`

#### HTML/MHTML Step 12 契约（2026-07-18 补充）

```python
# backend/app/parsers/web_fetcher.py
@dataclass(frozen=True)
class ScrapeResult:
    url: str
    final_url: str
    html: str
    visible_text: str
    page_title: str

def validate_public_url(url: str) -> None: ...
def scrape_url(url: str) -> ScrapeResult: ...

# backend/app/parsers/web_parser.py
def extract_markdown_from_html(html: str) -> str | None: ...
def build_visible_text_fallback(visible_text: str, page_title: str = "") -> str | None: ...

def html_to_markdown(
    html_content: str,
    image_aliases: dict[str, str] | None = None,
    base_location: str = "",
) -> str: ...

class WebParser(BaseParser):
    def __init__(self, title: str = "", **kwargs): ...
    def parse_into_text(self, content: bytes) -> Document: ...

# backend/app/parsers/mhtml_parser.py
class MHTMLParser(BaseParser):
    def __init__(self, *args, extract_images: bool = True, **kwargs): ...
    def parse_into_text(self, content: bytes) -> Document: ...
```

- `validate_public_url()` 仅允许 http/https，并拒绝 localhost、环回、私网、链路本地和保留 IP
- `scrape_url()` 启动 Chromium，等待 DOMContentLoaded + networkidle/正文字符阈值，返回渲染后 HTML、可见文本和标题
- `extract_markdown_from_html()` 使用 Trafilatura 输出 Markdown，保留图片/表格/链接，并适配微信公众号正文和图片 URL
- `WebParser` 解码 URL bytes，优先使用 Trafilatura；失败时回退 Playwright 可见文本
- `MHTMLParser` 使用 `email.message_from_bytes()`，选择体积最大的 `text/html` 部件作为正文
- MHTML 图片按 `Content-Location/Content-ID` 重写为 `images/...`，Base64 写入 `Document.images`
- Registry 注册 `html/htm -> WebParser`、`mhtml/mht -> MHTMLParser`

##### URL 入库衔接（Stage 5 完成抓取解析，持久化接入另立 Spec）

```text
用户提交 URL
→ WebUrlSourceAdapter 调用本阶段 WebParser/WebFetcher 下载或渲染网页
→ 原始 HTML 快照保存 MinIO，URL/ETag/Last-Modified 保存 Source.config/sync_cursor
→ 创建 Document 并进入解析队列
→ WebParser(html_bytes) 生成 Markdown Document
→ 分块、嵌入并写入 content_chunks
```

- 本阶段为复用 docreader 能力统一使用 Playwright，后续可增加 HTTP 快路径优化成本
- Fetcher 限制协议、内网地址、最终重定向地址、响应长度和超时，降低 SSRF/资源耗尽风险
- URL SourceAdapter 仍需独立 Spec 接入 API/MinIO/队列，保存原始 HTML 并创建 Document

#### EPUB/Image Step 13 契约（2026-07-19 补充）

```python
# backend/app/parsers/epub_parser.py
MAX_EPUB_MEMBER_SIZE = 32 * 1024 * 1024
MAX_EPUB_TOTAL_SIZE = 128 * 1024 * 1024
MAX_EPUB_COMPRESSION_RATIO = 100
MAX_EPUB_ENTRIES = 10_000

def validate_epub_archive(content: bytes) -> None: ...

class EPUBParser(BaseParser):
    def __init__(self, *args, extract_images: bool = True, **kwargs): ...
    def parse_into_text(self, content: bytes) -> Document: ...

# backend/app/parsers/image_parser.py
MAX_IMAGE_PIXELS = 40_000_000

class ImageParser(BaseParser):
    def parse_into_text(self, content: bytes) -> Document: ...
```

- `validate_epub_archive()` 验证 ZIP、`mimetype=application/epub+zip`、`META-INF/container.xml`、成员数、单成员大小、总解压大小和压缩比
- `EPUBParser` 使用 ebooklib 读取临时 `.epub`；按 spine 顺序输出 `## <章节标题>`，无 spine 时回退文档项顺序
- EPUB 元数据至少映射 `title/author/language/publisher/identifier`；输出补充 `format/file_size/chapter_count/image_count`
- EPUB 内嵌图片写入 `Document.images`，HTML 中相对路径重写为确定性的 `images/<文件名>`；`extract_images=False` 时不提取图片
- `ImageParser` 使用 Pillow 验证图片，输出原图 Markdown 引用和 Base64；元数据包含 `format/width/height/mode/file_size/exif/ocr_status`
- EXIF 使用可读标签名并把复杂值转成字符串，确保 Pydantic/JSON 可序列化；`ocr_status` 固定为 `not_configured`
- 图片声明像素超过 40,000,000 或输入无效时返回空 `Document` 和 `metadata.error`，不进入像素解码/OCR
- Registry 注册 `epub -> EPUBParser`；`png/jpg/jpeg/gif/webp/bmp/tif/tiff -> ImageParser`，不注册 Pillow 无法原生读取的 SVG
- 生产依赖新增 `ebooklib>=0.18`、`Pillow>=10.0.0`；不引入 pytesseract/Tesseract

#### 高级引擎 Step 14 契约（2026-07-19 补充）

```python
# backend/app/parsers/markitdown_parser.py
def markitdown_available() -> tuple[bool, str]: ...

class MarkitdownParser(BaseParser):
    def parse_into_text(self, content: bytes) -> Document: ...

# backend/app/parsers/opendataloader_parser.py
def opendataloader_available() -> tuple[bool, str]: ...

class OpenDataLoaderParser(BaseParser):
    def parse_into_text(self, content: bytes) -> Document: ...
```

- `markitdown_available()` 使用模块发现判断可选包是否存在，不在模块顶层 import `markitdown`
- `MarkitdownParser` 使用 `MarkItDown.convert(BytesIO(content), file_extension=...)`，保留 data URI，输出 `metadata.parser_engine=markitdown`
- MarkItDown 缺包、转换失败或空结果统一返回空 `Document` 和 `metadata.error`，不影响 builtin parser
- `opendataloader_available()` 同时检查 `java` 命令、Java 主版本 >= 11 和 `opendataloader_pdf` 包
- `OpenDataLoaderParser` 只接受 PDF；使用临时目录调用 `opendataloader_pdf.convert()` 生成 Markdown 和外置图片
- OpenDataLoader 收集输出目录内常见图片为 Base64，并把 Markdown 图片引用规范为 `images/<文件名>`
- OpenDataLoader 缺包、Java 不满足、转换失败或未生成 Markdown 时返回空 `Document` 和 `metadata.error`
- `backend/pyproject.toml` 新增 `[project.optional-dependencies].advanced`：`markitdown[docx,pdf,xls,xlsx]>=0.1.3`、`opendataloader-pdf>=2.4.7`
- `backend/app/parsers/__init__.py` 只导出两个类，不注册 file_type；多引擎路由留给 Step 15
- 本阶段继续使用“实现后统一测试”，不执行 TDD RED→GREEN

### §4.3 Implementation Checklist（20 个学习步骤）

> 每步格式：**教学要点** + **产出** + **验证**。每步独立可暂停。

#### 阶段 1：基础设施（Step 1-4）

- [ ] **Step 1：utils/endecode 编码处理**
  - 教学：为什么 parser 都需要编码处理（PDF 可能 GBK、网页可能 UTF-8 BOM）；`chardet` 检测 + `errors="replace"` 兜底
  - 产出：`backend/app/parsers/_utils/endecode.py`
  - 验证：`decode_bytes(b'\xc4\xe3\xba\xc3')` → `"你好"`（GBK）；`decode_bytes(b'\xef\xbb\xbfhello')` → `"hello"`（去 BOM）

- [ ] **Step 2：Document 数据契约**
  - 教学：Pydantic v2 BaseModel；为什么去 chunks；为什么用 `is_valid()` 而非 truthy
  - 产出：`backend/app/parsers/document.py` + `tests/test_parsers/test_document.py`
  - 验证：`Document().is_valid() == False`；`Document(content="x").is_valid() == True`

- [ ] **Step 3：BaseParser 抽象基类**
  - 教学：`abc.ABC` 阻止实例化；`@abstractmethod` 强制子类实现；模板方法模式（`parse()` 调 `parse_into_text()`）
  - 产出：`backend/app/parsers/base.py` + `tests/test_parsers/test_base.py`
  - 验证：`BaseParser()` 抛 TypeError；子类不实现 `parse_into_text` 抛 TypeError

- [ ] **Step 4：TextParser（第一个具体 parser）**
  - 教学：BaseParser 的最小实现；`parse_into_text` 调 `endecode.decode_bytes`；构造函数继承
  - 产出：`backend/app/parsers/text_parser.py` + `tests/test_parsers/test_text_parser.py`
  - 验证：`TextParser(file_name="a.txt").parse(b"hello")` → `Document(content="hello")`

#### 阶段 2：注册表 + 接入（Step 5-6）

- [x] **Step 5：ParserRegistry 简化版（单 key）** ✅ 2026-07-16
  - 教学：注册表模式 vs 全局字典（封装 + 列举能力）；按 file_type 派发
  - 产出：`backend/app/parsers/registry.py`（简化版） + `tests/test_parsers/test_registry.py`
  - 验证：`reg.register("txt", TextParser)` + `reg.get_parser_class("txt")` → TextParser；`reg.list_supported()` → `["txt"]`

- [x] **Step 6：接入 backend + 删旧占位** ✅ 2026-07-16
  - 教学：消费方迁移；同 PR 内删旧文件避免双份维护
  - 产出：改 `backend/app/workers/parse_document.py`；删 `backend/app/workers/parsers.py`
  - 验证：`pytest tests/test_document.py` 仍通过（MD 上传 → processed） — ⚠ 单元层通过；端到端待用户在 docker 环境验证

#### 阶段 3：基础格式（Step 7-9）

- [x] **Step 7：MarkdownParser 最简版** ✅ 2026-07-16
  - 教学：先用最简 decode 跑通；为 Step 19 升级 PipelineParser 留对比
  - 产出：`backend/app/parsers/markdown_parser.py`（初版，仅 decode）
  - 验证：`MarkdownParser().parse(b"# title")` → `Document(content="# title")`

- [x] **Step 8：Word 系列（Docx2Parser + DocParser）** ✅ 2026-07-16
  - 教学：python-docx 解析段落；老式 .doc 用 antiword/catdoc 命令行
  - 产出：`backend/app/parsers/docx2_parser.py` + `doc_parser.py` + 测试
  - 验证：`.docx` 文件 → 段落 + 表格拼接；`.doc` 文件 → antiword/catdoc 文本

- [x] **Step 9：PdfParser（pdfplumber）** ✅ 2026-07-16
  - 教学：pdfplumber 逐页提取；表格 PDF 的挑战（声明技术限制）
  - 产出：`backend/app/parsers/pdf_parser.py` + 测试
  - 验证：文字版 PDF → 全文文本；扫描版 PDF → 空文本（OCR 留 Stage 7）

#### 阶段 4：Office 套件（Step 10-11）

- [x] **Step 10：表格套件（XLSX / XLS / CSV）** ✅ 2026-07-18
  - 教学：三种存储结构；Registry 按格式派发；不依赖 LibreOffice 的原生解析；学习版资源限制
  - 产出：`excel_parser.py` + `xls_parser.py` + `csv_parser.py` + `excel_convert.py` + `xlsx_merge.py` + `xlsx_repair.py`
  - [x] 10.1 Registry 暂时仅注册 `.xlsx`，移除不可靠格式广告 ✅ 2026-07-18
  - [x] 10.2 删除 LibreOffice 查找/子进程转换；TDD 验证非 XLSX 不启动外部程序并明确失败 ✅ 2026-07-18
  - [x] 10.3 新增 `XlsParser`（xlrd）及多 Sheet 测试，注册 `.xls` ✅ 2026-07-18
  - [x] 10.4 新增 `CsvParser`（标准库 csv）及编码/分隔符测试，注册 `.csv` ✅ 2026-07-18
  - [x] 10.5 固化最终 Registry 契约：`.xlsx/.xls/.csv` 分别路由；`.xlsb/.ods/.et` 拒绝 ✅ 2026-07-18
  - [x] 10.6 增加学习版资源限制：XLSX ZIP 大小/压缩比、XLSX/XLS 单元格数、CSV 行列数 ✅ 2026-07-18
  - [x] 10.7 更新依赖（`xlrd>=2.0.1`）并运行全部 parser 回归 ✅ 2026-07-18
  - 验证：三种格式均输出 Markdown；Registry 只列出三种表格格式；解析过程不启动 LibreOffice

- [x] **Step 11：PPTX 套件（2 文件）** ✅ 2026-07-18
  - 教学：python-pptx 遍历 slides/shapes；PPTX ZIP 媒体抽取；文本与二进制媒体分离
  - 产出：`ppt_convert.py` + `pptx_media.py` + `test_ppt_parser.py`
  - [x] 11.1 TDD 固化 PPTX 文本、媒体和 Registry 契约 ✅ 2026-07-18
  - [x] 11.2 实现 `extract_pptx_media()`，媒体写入 `Document.images` ✅ 2026-07-18
  - [x] 11.3 实现 `PptxParser` 与 `normalize_pptx_bytes()`，拒绝旧 `.ppt` ✅ 2026-07-18
  - [x] 11.4 注册 `.pptx`，更新 `python-pptx>=1.0.0` 依赖 ✅ 2026-07-18
  - [x] 11.5 运行 PPT 专项、Ruff 和全部 Parser 回归 ✅ 2026-07-18
  - 验证：`.pptx` → 分幻灯片文本 + 媒体路径；`.ppt` → Registry `KeyError`

#### 阶段 5：网页与邮件（Step 12）

- [x] **Step 12：URL/WebParser + MHTMLParser** ✅ 2026-07-18
  - 教学：Playwright 动态渲染；Trafilatura 正文提取；微信文章适配；MIME multipart；图片引用重写
  - 产出：`web_fetcher.py` + `web_parser.py` + `mhtml_parser.py` + 契约测试
  - [x] 12.1 TDD 固化 URL 校验、HTML 正文提取、微信正文/图片规则和可见文本 fallback ✅
  - [x] 12.2 实现同步 Playwright `scrape_url()` 与 `WebParser`（URL bytes → Document）✅
  - [x] 12.3 TDD 固化 MHTML 主正文选择、图片提取与引用重写契约 ✅
  - [x] 12.4 实现 `MHTMLParser`，注册 `.mhtml/.mht` ✅
  - [x] 12.5 更新 playwright/trafilatura/beautifulsoup4/markdownify/lxml 依赖与 Docker Chromium 安装 ✅
  - [x] 12.6 运行 helper 单测、本地 Playwright 页面验收、Ruff 和全部 Parser 回归 ✅
  - 验证：普通/微信 HTML → 正文 Markdown；动态页面 → 渲染后正文；MHTML → Markdown + `Document.images`

#### 阶段 6：富文档（Step 13）

- [x] **Step 13：EPUBParser + ImageParser** ✅ 2026-07-19
  - 教学：ebooklib 遍历 spine；Pillow 抽取 EXIF + 简单 OCR 占位
  - 产出：`epub_parser.py` + `image_parser.py`
  - [x] 13.1 实现 `validate_epub_archive()` 与 `EPUBParser` ✅
  - [x] 13.2 实现 Pillow `ImageParser`，OCR 仅输出 `not_configured` 占位 ✅
  - [x] 13.3 注册 EPUB 和 Pillow 支持的独立图片格式，更新生产依赖 ✅
  - [x] 13.4 补充 EPUB/图片契约测试 ✅
  - [x] 13.5 统一运行专项测试、Ruff 和全部 Parser 回归 ✅
  - 验证：`.epub` → 章节文本；`.jpg` → metadata dict

#### 阶段 7：高级引擎（Step 14）

- [x] **Step 14：MarkitdownParser + OpenDataLoaderParser** ✅
  - 教学：高级引擎抽象；外部依赖按需安装策略；`check_available` 函数
  - 产出：`markitdown_parser.py` + `opendataloader_parser.py`（完整可选适配器，不加入默认 Registry）
  - [x] 14.1 实现 MarkItDown 可用性检查、惰性加载和 bytes → Markdown ✅
  - [x] 14.2 实现 OpenDataLoader Java/包检查、PDF 转换、图片收集与引用重写 ✅
  - [x] 14.3 导出两个高级 Parser，新增 `advanced` 可选依赖组 ✅
  - [x] 14.4 补充可用/不可用、转换成功/失败、图片重写和临时目录清理测试 ✅
  - [x] 14.5 统一运行高级引擎专项、Ruff 和全部 Parser 回归 ✅
  - 验证：缺依赖时模块仍可导入并明确返回 unavailable；依赖存在或测试替身下输出 Markdown Document

#### 阶段 8：注册表升级（Step 15）

- [x] **Step 15：Registry 双 key + builtin 兜底** ✅ 2026-07-19
  - 教学：嵌套字典 `Dict[engine, Dict[file_type, parser]]`；fallback 到 builtin；`list_engines` 列举能力
  - 产出：升级 `registry.py`、`parsers/__init__.py`、`test_registry.py`
  - [x] 15.1 先写/改 Registry 测试，覆盖双 key 命中、未知 engine/不支持格式回退 builtin、最终未知格式抛 `KeyError`、单参数兼容入口 ✅
  - [x] 15.2 实现 `ParserEngineRegistry` 的规范化、整表校验、注册、查询、`list_supported()` 与兼容别名 ✅
  - [x] 15.3 实现 `list_engines()` / `get_engine_names()`，覆盖可用、不可用、探针异常和稳定排序 ✅
  - [x] 15.4 改造 `_register_defaults()`：注册 builtin 全量格式、markitdown 多格式、opendataloader PDF；导出 `BUILTIN_ENGINE / ParserEngineRegistry / ParserRegistry` ✅
  - [x] 15.5 运行 `test_registry.py`、全部 parser 回归和本阶段 Ruff；记录结果与 Plan-Execution Diff ✅
  - 验证：`get_parser_class("markitdown", "pdf")` → `MarkitdownParser`；`get_parser_class("unknown", "pdf")` → `PdfParser`；`get_parser_class("pdf")` → `PdfParser`；未知格式保持 `KeyError`

#### 阶段 9：Markdown utils（Step 16-17）

- [x] **Step 16：MarkdownTableFormatter** ✅ 2026-07-19
  - 教学：GFM 表格规范；正则标准化对齐 + 间距；处理 MarkItDown 的伪前缀行
  - 产出：`markdown_parser.py` 加 `MarkdownTableUtil` + `MarkdownTableFormatter`
  - 验证：歪斜表格 → 标准 GFM

- [x] **Step 17：MarkdownImageBase64** ✅ 2026-07-19
  - 教学：Base64 图片抽取；`data:image/png;base64,...` 解析；生成 UUID 文件名
  - 产出：`markdown_parser.py` 加 `MarkdownImageUtil` + `MarkdownImageBase64`；`endecode.encode_image`
  - 验证：含 base64 的 markdown → 文本 + images dict

#### 阶段 10：ChainParser（Step 18-19）

- [x] **Step 18：FirstParser + PipelineParser** ✅ 2026-07-19
  - 教学：责任链 vs 管道的区别；`type()` 动态生成子类（工厂方法）
  - 产出：`backend/app/parsers/chain.py` + `tests/test_parsers/test_chain.py`
  - 验证：`FirstParser.create(A, B)` try A 失败 try B；`PipelineParser.create(A, B)` A 输出喂 B

- [x] **Step 19：MarkdownParser 升级为 PipelineParser** ✅ 2026-07-19
  - 教学：组合模式价值——把胖 parser 拆成阶段用管道串起来
  - 产出：升级 `markdown_parser.py` 为 `PipelineParser(TableFormatter, ImageBase64)`
  - 验证：含表格 + base64 的 markdown → 标准化 + 抽取

#### 阶段 11：测试 + 收尾（Step 20）

- [x] **Step 20：完整测试 + 接入验证** ✅ 2026-07-19
  - 教学：契约测试 vs 实现测试；派发逻辑与 worker/DB 解耦
  - 产出：`parsers/dispatch.py`（支持 engine）；`parse_document.py` 接入；补全 chain/markdown/dispatch 测试
  - 验证：`pytest tests/test_parsers/` → `130 passed, 1 skipped`

### §4.4 Spec Review Notes（自评）

| Check | Verdict | Evidence |
|---|---|---|
| Requirement clarity & acceptance | PASS | §1 Goal / In-Scope / Out-of-Scope / 验收标准清晰；§0 Q1-Q7 全部决策 |
| Plan executability | PASS | §4.1 22 文件结构完整；§4.2 关键签名；§4.3 20 步 checklist 每步有教学要点 + 产出 + 验证 |
| Risk / rollback readiness | PARTIAL | 风险低（学习型任务）；回滚策略：每步独立可 revert（git commit per step） |

- **Readiness Verdict**：**GO**（建议性）
- **Risks**：
  1. Markitdown / OpenDataLoader 外部依赖未装时 Step 14 只能写骨架（用户可接受）
  2. PPT 媒体抽取依赖 python-pptx 对视频格式的支持，可能有边角 case
  3. 20 步走完预计 20-30 小时学习时间，需要分多个会话完成
- **Phase Reminders**：Execute 阶段需在 §5 记录每步教学要点 + 用户理解验证

### §4.5 Stage-Gate Execution Protocol

> 2026-07-15 用户决策：每个阶段完成后必须经用户审批，才可进入下一阶段。**不允许一次性跑完所有阶段。**

#### 11 个 Stage Gate

| Gate | 当前阶段完成 | 进入下一阶段前必须得到 |
|------|------------|---------------------|
| Gate 1 | Stage 1（Step 1-4 基础设施）完成 | 用户明确批准 |
| Gate 2 | Stage 2（Step 5-6 注册+接入）完成 | 用户明确批准 |
| Gate 3 | Stage 3（Step 7-9 基础格式）完成 | 用户明确批准 |
| Gate 4 | Stage 4（Step 10-11 Office 套件）完成 | 用户明确批准 |
| Gate 5 | Stage 5（Step 12 网页邮件）完成 | 用户明确批准 |
| Gate 6 | Stage 6（Step 13 富文档）完成 | 用户明确批准 |
| Gate 7 | Stage 7（Step 14 高级引擎）完成 | 用户明确批准 |
| Gate 8 | Stage 8（Step 15 注册表升级）完成 | 用户明确批准 |
| Gate 9 | Stage 9（Step 16-17 Markdown utils）完成 | 用户明确批准 |
| Gate 10 | Stage 10（Step 18-19 ChainParser）完成 | 用户明确批准 |
| Gate 11 | Stage 11（Step 20 收尾）完成 | 进入 Review 阶段 |

#### 阶段完成的判定标准（每 Gate 必须满足）

1. 该阶段所有 Step 的"产出"文件已创建/修改
2. 该阶段所有 Step 的"验证"项已通过（测试或手动验证）
3. §5 Execute Log 已记录该阶段的：
   - 实际改动摘要
   - 教学要点回顾（用户能复述关键概念）
   - 偏差说明（如有）
4. 用户口述确认理解了该阶段的核心概念

#### 阶段审批话术

- Agent 在阶段最后一个 Step 完成后，**必须暂停**，输出：
  - "Stage N 完成。产出：[文件列表]。验证：[结果]。教学要点回顾：[核心概念]。"
  - "回复 `Stage N Approved` 进入 Stage N+1，或指出需要调整的点。"
- 用户未明确批准前，**禁止开始下一阶段的任何 Step**

#### 跨会话恢复

- 因学习任务可能跨多个会话，每次会话开始时 Agent 必须先读 spec §5 Execute Log + TaskList 确认当前进度
- 找到当前所在阶段 + 下一个待执行 Step
- 如有歧义，向用户确认后再继续

---

## §5 Execute Log

### Stage 1：基础设施（Step 1-4）[完成 2026-07-15]

#### 产出文件

| 文件 | 行数 | 内容 |
|------|------|------|
| `backend/app/parsers/__init__.py` | 8 | 包入口（当前只导出 endecode，后续 Step 累加） |
| `backend/app/parsers/_utils/__init__.py` | 4 | utils 包入口 |
| `backend/app/parsers/_utils/endecode.py` | ~50 | `decode_bytes`（fallback chain）+ `encode_bytes`（UTF-8） |
| `backend/app/parsers/document.py` | ~30 | `Document` Pydantic 模型（content + images + metadata，去 chunks） |
| `backend/app/parsers/base.py` | ~50 | `BaseParser` abc.ABC + `parse_into_text` 抽象 + `parse` 模板方法 |
| `backend/app/parsers/text_parser.py` | ~20 | `TextParser`：bytes → Document |
| `backend/tests/test_parsers/test_document.py` | ~40 | 5 个 Document 契约测试 |
| `backend/tests/test_parsers/test_base.py` | ~60 | 6 个 BaseParser 行为测试 |
| `backend/tests/test_parsers/test_text_parser.py` | ~40 | 6 个 TextParser 测试 |

#### 验证结果

```
tests/test_parsers/ — 17 passed in 0.22s
```

- `decode_bytes(b'\xc4\xe3\xba\xc3')` → `'你好'`（GBK fallback 生效）
- `decode_bytes(b'\xef\xbb\xbfhello')` → `'﻿hello'`（BOM 保留，忠实复刻 docreader）
- `decode_bytes(b'\xff\xfe\x00\x01')` → latin-1 兜底，不抛异常
- `Document().is_valid() == False`，`Document(content="x").is_valid() == True`
- `BaseParser()` 抛 TypeError，子类不实现 `parse_into_text` 抛 TypeError
- `TextParser(file_name="a.txt").parse(b"hello")` → `Document(content="hello")`

#### 教学要点回顾（Stage 1 核心）

| 概念 | 用户应能口述 |
|------|------------|
| **编码 fallback chain** | 为什么 utf-8 → gb18030 → ... → latin-1 这个顺序；latin-1 兜底的特殊性 |
| **Document 契约** | 为什么统一返回类型（消费方不需要写 if-elif）；为什么去 chunks 字段 |
| **BaseParser 抽象基类** | abc.ABC 阻止实例化 / @abstractmethod 强制子类 / 模板方法 parse() 的价值 |
| **TextParser** | 最简实现验证抽象；继承 BaseParser 的 __init__ |

#### 偏差说明

- **endecode 图片函数未移植**：原版 `decode_image` / `encode_image` 依赖 numpy + Pillow，但 Stage 1 不需要图片处理。留到 Step 17（MarkdownImageBase64）按需移植。
- **BOM 处理**：忠实复刻 docreader 不剥离 BOM（保留 `﻿`）。如果未来发现影响 markdown 渲染，加 `"utf-8-sig"` 到 encodings 列表第一位即可。

#### Git commit 建议

Stage 1 完成可作为一个原子 commit：
```
feat(parsers): Stage 1 基础设施（endecode + Document + BaseParser + TextParser）

- 移植 docreader/utils/endecode.py（仅文本函数，图片留 Step 17）
- Document 裁剪版（content + images + metadata，去 chunks）
- BaseParser 抽象基类（abc.ABC + 模板方法）
- TextParser 第一个具体 parser（验证抽象）
- 17 个测试全过
```

---

### Stage 2：注册表 + 接入 backend（Step 5-6）[完成 2026-07-16]

#### 用户决策（Gate 1 → Stage 2）

- **Stage 1 Approved**：2026-07-16 用户批准
- **选项 A**：`.md` 暂时走 TextParser（不提前写极简 MarkdownParser，留给 Step 7 教学）

#### 产出文件

| 文件 | 行数 | 变化 | 内容 |
|------|------|------|------|
| `backend/app/parsers/registry.py` | ~70 | 新增 | `ParserRegistry` 单 key 版（register / get_parser_class / list_supported）+ 模块级单例 `registry` |
| `backend/app/parsers/__init__.py` | ~26 | 改 | 导出 Document/BaseParser/registry/TextParser + `_register_defaults()` 注册 txt/md/markdown |
| `backend/app/workers/parse_document.py` | +20 行 | 改 | import 切换 + 调用改为 `_parse_to_text()`（封装 Registry 派发 + KeyError 兜底 TextParser） |
| `backend/app/workers/parsers.py` | -62 行 | **删除** | 旧 if-elif 占位代码 |
| `backend/tests/test_parsers/test_registry.py` | ~120 | 新增 | 12 个 Registry 单元测试 |

#### 验证结果

**单元层（全部通过）**：
```
tests/test_parsers/ — 29 passed in 0.11s
  ├─ test_base.py        6 passed
  ├─ test_document.py    5 passed
  ├─ test_registry.py   12 passed（新增）
  └─ test_text_parser.py 6 passed
```

**Registry 端到端模拟（通过）**：
- `registry.list_supported()` → `['markdown', 'md', 'txt']`
- `registry.get_parser_class('md')` → TextParser（选项 A）
- MD bytes → Document.content 正确，含标题/中文/英文
- 未知扩展名（.log）兜底 TextParser
- `.markdown` 别名兜底 TextParser

**端到端 `test_document.py`（待用户验证）**：
- 该测试依赖 Postgres + MinIO + Redis + worker 进程 + embedding API
- 按 CLAUDE.md "禁止启动开发服务器"约束，未在本次执行中运行
- 已通过隔离单测验证 `_parse_to_text` 逻辑等价于旧 `parse_by_filename`
- ⚠ **用户在完整 docker 环境（`docker-compose up`）下需补跑一次确认**

#### 教学要点回顾（Stage 2 核心）

| 概念 | 用户应能口述 |
|------|------------|
| **注册表模式 vs 全局字典** | 封装（BaseParser 子类校验）+ 列举能力（`list_supported()`）+ 多实例可隔离 |
| **单 key → 双 key 渐进式抽象** | 一次只引入一个新概念；双 key 留到 Step 15（多引擎场景） |
| **KeyError vs 内置兜底** | Registry 保持"纯查表"语义，兜底策略由消费方决定（`_parse_to_text` 内 try/except） |
| **同 PR 删旧代码** | 避免双份维护的 tech debt；grep 确认零外部调用方后删除 |
| **签名变化的代价** | 旧 `parse_by_filename → str`；新 `parser.parse → Document`，消费方取 `.content` |

#### 偏差说明

1. **Registry 加了 `register` 时的 BaseParser 子类校验**：spec §4.2 没明确要求，但作为"封装价值"的教学示例主动加上。`issubclass(parser_cls, BaseParser)` + `isinstance(parser_cls, type)` 双重检查（同时挡住"传实例而非类"的错误）。
2. **重复注册打 warning 而非抛错**：spec 没规定，选择 warning 是为了允许"重新配置"场景（如测试中重置默认 parser），同时帮助发现意外的覆盖。
3. **`_parse_to_text` 是模块私有函数**：spec §4.3 Step 6 只说"改 parse_document.py"，没规定封装方式。选择独立函数（而非 inline）是为了：① 单元可测；② 未来扩展（如加 engine 参数）只改一处。

#### Git commit 建议

Stage 2 完成可作为一个原子 commit：
```
feat(parsers): Stage 2 Registry + 接入 backend（删旧 workers/parsers.py）

- 新增 ParserRegistry（单 key 版）+ 模块级单例
- __init__.py 注册默认 parser（选项 A：txt/md/markdown 都走 TextParser）
- parse_document.py 接入 Registry，KeyError 兜底 TextParser
- 删除旧 workers/parsers.py（if-elif 占位）
- 12 个 Registry 单元测试，全过
```

---

### Stage 3：基础格式（Step 7-9）[完成 2026-07-16]

#### 用户决策（Gate 2 → Stage 3）

- **Stage 2 Approved**：2026-07-16 用户批准（"继续下一阶段"）
- **范围**：Step 7 MarkdownParser 最简版 / Step 8 Word 系列 / Step 9 PdfParser

#### 产出文件

| 文件 | 行数 | 变化 | 内容 |
|------|------|------|------|
| `backend/app/parsers/markdown_parser.py` | ~28 | 新增 | `MarkdownParser` 最简版（仅 decode → Document），为 Step 19 PipelineParser 升级留对比基线 |
| `backend/app/parsers/docx2_parser.py` | ~65 | 新增 | `Docx2Parser`：python-docx 段落 + 表格（移植 `_parse_using_simple_method`） |
| `backend/app/parsers/doc_parser.py` | ~90 | 新增 | `DocParser`：antiword/catdoc 命令行 + tempfile + fallback metadata |
| `backend/app/parsers/pdf_parser.py` | ~75 | 新增 | `PdfParser`：pdfplumber 逐页 extract_text 拼接 + page_count metadata |
| `backend/app/parsers/__init__.py` | ~45 | 改 | 追加 .docx/.doc/.pdf 注册；导出 4 个新 parser 类 |
| `backend/pyproject.toml` | +1 行 | 改 | 显式声明 `python-docx>=1.0.0`（原本未列入但已安装） |
| `backend/tests/test_parsers/test_markdown_parser.py` | ~75 | 新增 | 9 个 MarkdownParser 测试（含与 TextParser 行为等价验证） |
| `backend/tests/test_parsers/test_docx_parser.py` | ~75 | 新增 | 7 个 Word 系列测试（Docx2Parser 5 + DocParser 2 含 skip） |
| `backend/tests/test_parsers/test_pdf_parser.py` | ~80 | 新增 | 5 个 PDF 测试（含手写最小 PDF bytes 构造器） |

#### 验证结果

**全部 parser 测试**：
```
tests/test_parsers/ — 48 passed, 1 skipped in 0.51s
  ├─ test_base.py              6 passed
  ├─ test_document.py          5 passed
  ├─ test_docx_parser.py       6 passed + 1 skipped
  │   └─ SKIPPED: test_no_tool_returns_error_metadata（本机装了 antiword）
  ├─ test_markdown_parser.py   9 passed
  ├─ test_pdf_parser.py        5 passed
  ├─ test_registry.py         12 passed
  └─ test_text_parser.py       6 passed
```

**Registry 端到端派发（通过）**：
- `list_supported()` → `['doc', 'docx', 'markdown', 'md', 'pdf', 'txt']`（6 个扩展名，字典序）
- `md` → MarkdownParser；`markdown` → MarkdownParser；`txt` → TextParser
- `docx` → Docx2Parser；`doc` → DocParser；`pdf` → PdfParser

**MarkdownParser 验证**：
- `MarkdownParser().parse(b"# title\n\nhello")` → `Document(content="# title\n\nhello")`
- GBK 编码中文 markdown 经 fallback chain 正确解码
- markdown 语法字符（`#` / `*` / `|` / `[]`）原样保留（本阶段不做格式化）
- 与 TextParser 输出 byte-for-byte 等价（升级 Step 19 时删该等价测试）

**Docx2Parser 验证**：
- `_build_docx_bytes(["第一段", "第二段"])` → 两段文本被 `\n\n` 拼接
- `_build_docx_bytes(table_rows=[["姓名","年龄"],["张三","25"]])` → `"姓名 | 年龄"` + `"张三 | 25"` 行
- 空/空白段落被 strip 过滤
- 非法 bytes（`b"not a real docx"`）→ `Document(content="", metadata={"error": "open_failed: ..."})`，不抛异常

**DocParser 验证**：
- 本机有 antiword（`D:\software\Git\mingw64\bin\antiword.EXE`），可走真实命令行路径
- 找不到 antiword/catdoc 时 → `Document(content="", metadata={"error": "no_doc_tool", "tried": ["antiword", "catdoc"]})`
- subprocess 60s 超时；tempfile 用完 unlink

**PdfParser 验证**：
- 手写最小 PDF 1.4（`%PDF-1.4` + Catalog + Page + Content stream + Helvetica font）→ pdfplumber 成功 extract_text
- metadata 记录 `page_count` + `text_page_count`（供消费方判断扫描版比例）
- 非法 bytes / 空 bytes → `open_failed` 错误 metadata，不抛异常
- **技术限制声明**（docstring）：扫描版 PDF 无文字层；表格结构扁平化；多栏排版可能错位（OCR / layout 分析留 Stage 7 / P4）

#### 教学要点回顾（Stage 3 核心）

| 概念 | 用户应能口述 |
|------|------------|
| **MarkdownParser 行为等价但身份独立** | 为什么不直接复用 TextParser（类型派发正确 + 后续 utils 挂载扩展点） |
| **"最简版→升级版"渐进式抽象** | Step 7 最简版刻意保留，Step 19 PipelineParser 才能展示"胖 parser 拆阶段"的价值 |
| **Docx2Parser 用 BytesIO + python-docx** | 不写临时文件；paragraphs + tables 双重遍历；表格 cell 用 `\|` join |
| **DocParser 命令行 + fallback metadata** | 不引入重依赖 textract；找不到工具不抛异常，由消费方决策 |
| **PdfParser 技术限制声明** | 扫描版 / 表格 / 多栏——三个明确边界，OCR 和 layout 留 Stage 7 / P4 |
| **错误路径统一返回 Document + metadata.error** | 不抛异常 → 消费方按 metadata 决策（重试 / 报警 / 兜底） |

#### 偏差说明

1. **DocParser 不走 docreader 的 doc→docx 转换路径**：原版先转 docx 再走 DocxParser（含图像抽取），依赖 libreoffice。Stage 3 学习阶段不做图像，简化为 antiword/catdoc 直接抽文本。需要图像时回到 docreader 原版（或用 Stage 14 高级引擎）。
2. **不引入 textract**：docreader 自己已因 SSRF 风险注释掉 `_parse_with_textract`。Stage 3 直接放弃该路径。
3. **PdfParser 不调 `extract_tables`**：spec Step 9 教学要点是"声明表格 PDF 技术限制"而非"实现表格抽取"。如果调 extract_tables 会引入多嵌套表格不稳定的失败 case，违背"最简版"原则。表格标准化留给 Step 16 的 MarkdownTableFormatter（统一在 markdown 层做）。
4. **手写最小 PDF 1.4 作为 test fixture**：项目无 PDF 生成库（reportlab / fpdf2 都没装），引入任一会增加依赖。手写 PDF 模板硬编码 stream length，**改动模板需重新对齐字节数**——在测试文件注释里标注了。
5. **`python-docx` 加入 pyproject.toml**：原本未列入但已全局安装；为可重现性显式声明 `>=1.0.0`。
6. **MarkdownParser 与 TextParser 等价测试**：spec 没要求，主动加 `TestMarkdownParserVsTextParser` 类作为"行为等价"教学锚点；Step 19 升级时该类需删除（注释里标了）。

#### Git commit 建议

Stage 3 完成可作为一个原子 commit：
```
feat(parsers): Stage 3 基础格式（Markdown / Word / PDF）

- MarkdownParser 最简版（decode → Document），为 Step 19 PipelineParser 留对比基线
- Docx2Parser（python-docx 段落 + 表格 cell join）
- DocParser（antiword/catdoc 命令行 + tempfile + fallback metadata）
- PdfParser（pdfplumber 逐页 extract_text + page_count metadata）
- pyproject.toml 显式声明 python-docx>=1.0.0
- Registry 注册 .docx / .doc / .pdf，6 个扩展名完整派发
- 21 个新测试（Markdown 9 + Word 6+1skip + PDF 5），全过
```

---

### Stage 4：Office 套件（Step 10-11）[进行中 2026-07-17]

#### 用户决策（Gate 3 → Stage 4）

- **Stage 3 Approved**：2026-07-17 用户明确指令“进入下一个阶段”
- **执行策略**：遵循默认单步执行，本轮只执行 Step 10（Excel 套件）；Step 11（PPT 套件）等待下一次继续指令
- **TDD 状态**：准备进入 RED，先新增 Excel 套件契约测试并确认因实现缺失而失败

#### 2026-07-18 Step 10 WIP 诊断与反向同步

- **诊断结果**：实现已创建 4 个 Excel 文件，但测试与实现存在契约冲突，按协议暂停 Execute 并退回 Plan
- **契约冲突**：实现注册 `.xlsx/.xls/.xlsb/.ods/.et`，测试要求默认只注册 `.xlsx`
- **安全缺口**：`validate_xlsx_archive()` 与 `_validate_sheet_dimensions()` 尚未实现；ZIP 读取处仍有资源耗尽 TODO
- **验证阻塞**：当前 Python 3.13 环境缺少 `openpyxl`，pytest 在收集 `test_excel_parser.py` 时失败
- **Plan 修订**：见 Q9、§4.2 Excel 安全契约、§4.3 Step 10.1-10.6
- **审批门禁**：收到精确 `Plan Approved` 前不继续修改实现

#### 2026-07-18 Plan 审批与执行方式

- **Plan Approved**：用户已给出精确审批指令，恢复 Execute
- **执行方式**：本任务为简单学习任务，仅使用 `test-driven-development`；用户明确要求不同时使用 `subagent-driven-development`
- **当前单步**：只执行 Step 10.1，完成后按默认单步策略暂停

#### Step 10.1：默认 Registry 仅开放 XLSX [完成 2026-07-18]

- **TDD RED**：`test_registry_does_not_advertise_formats_requiring_libreoffice` 产生 4 个预期失败；`.xls/.xlsb/.ods/.et` 均未抛 `KeyError`
- **最小实现**：`backend/app/parsers/__init__.py` 仅注册 `xlsx -> ExcelParser`，同步公共 API 说明
- **TDD GREEN**：XLSX 正向路由 + 4 个非 XLSX 拒绝测试，`5 passed`
- **回归验证**：`test_registry.py` + Excel Registry 契约，`17 passed`
- **偏差**：无；未触碰 Step 10.2-10.6
- **当时的下一步**：等待用户“继续”后执行旧版 Step 10.2；后续已被“表格格式范围二次修订”取代

#### 2026-07-18 表格格式范围二次修订

- **用户决策**：表格解析只支持 `.xlsx/.xls/.csv`，不支持 `.xlsb/.ods/.et`
- **技术决策**：XLSX 使用 openpyxl；XLS 使用 xlrd；CSV 使用标准库 csv；不使用 LibreOffice
- **Plan 变更**：Step 10.2-10.7 已按三个独立 Parser 重写，见 Q10、§4.1-§4.3
- **状态**：范围发生实质变化，退回 Plan；此前 `Plan Approved` 不自动覆盖新 Plan
- **审批门禁**：收到新的精确 `Plan Approved` 后，从 Step 10.2 恢复 TDD 单步执行

#### Step 10.2：删除 LibreOffice 转换路径 [完成 2026-07-18]

- **Plan Approved**：用户再次给出精确审批指令，恢复 Execute
- **TDD RED**：新契约测试因 `find_soffice` 仍存在而按预期失败
- **最小实现**：删除 `find_soffice()`、`convert_excel_to_xlsx_bytes()` 及 `os/shutil/subprocess/tempfile/pathlib` 依赖
- **行为契约**：`normalize_excel_bytes()` 只返回原生 XLSX；其他输入抛出包含 `external conversion is disabled` 的 `ValueError`
- **TDD GREEN**：核心契约 `3 passed`；其余 Excel 契约 `17 passed, 2 deselected`；Registry 回归 `12 passed`
- **未运行**：本机未安装 `ruff`；Step 10.6 的两个未来安全测试按计划暂不计入本步
- **偏差**：无；未开始 `XlsParser`
- **下一步**：等待用户“继续”后执行 Step 10.3

#### 2026-07-18 Step 10 批量执行授权

- **用户指令**：“下一阶段要做什么，合在一起做了”
- **批量范围**：Step 10.3-10.7（XlsParser、CsvParser、最终 Registry、学习版资源限制、全量 Parser 回归）
- **范围边界**：不进入 Step 11（PPT 套件）
- **执行方式**：仍按 TDD 在内部逐项 RED/GREEN，但不在子步骤之间等待用户确认

#### Step 10.3-10.7：表格套件批量收口 [完成 2026-07-18]

##### 产出

- `backend/app/parsers/xls_parser.py`：xlrd 读取 BIFF XLS，多 Sheet 输出 Markdown，处理数字/布尔/日期
- `backend/app/parsers/csv_parser.py`：编码回退、逗号/分号/Tab 嗅探、Markdown 输出
- `backend/app/parsers/__init__.py`：最终注册 `.xlsx/.xls/.csv`；拒绝 `.xlsb/.ods/.et`
- `backend/app/parsers/xlsx_repair.py`：`validate_xlsx_archive()` 资源校验
- `backend/app/parsers/excel_parser.py`：`_validate_sheet_dimensions()` 工作表校验
- `backend/app/parsers/xlsx_merge.py`：读取前执行 ZIP/维度校验，并确保 workbook 关闭
- `backend/pyproject.toml`：生产依赖 `xlrd>=2.0.1`；测试依赖 `xlwt>=1.3.0`
- `backend/tests/test_parsers/test_xls_parser.py` / `test_csv_parser.py`：真实内存样本契约测试

##### 学习版限制

- XLSX：单 ZIP 成员最多 32 MB，总解压大小最多 128 MB，压缩比最多 100
- XLSX/XLS：单工作表声明单元格最多 1,000,000
- CSV：最多 100,000 行、1,000 列

##### TDD 与验证

- **XLS RED**：`4 failed`（`app.parsers.xls_parser` 缺失）→ **GREEN**：XLS + Excel 契约 `20 passed`
- **CSV RED**：`5 failed`（`app.parsers.csv_parser` 缺失）→ **GREEN**：XLS + CSV `9 passed`
- **资源限制 RED**：3 个缺失护栏测试失败 → **GREEN**：`3 passed`
- **表格专项 + Registry**：`40 passed`
- **全部 Parser 回归**：`77 passed`
- **Ruff**：本批次文件 `All checks passed`

##### 偏差与下一步

- **偏差**：为生成真实 `.xls` 测试样本，增加仅开发依赖 `xlwt`；不进入生产解析路径
- **Step 10 结论**：PASS
- **下一步**：停在 Step 11 前；PPT 套件不在本次批量授权范围内

#### 2026-07-18 Step 11 启动

- **用户授权**：“现在进入下一个阶段”
- **当前范围**：只完成 PPTX 文本和媒体解析；不支持旧 `.ppt`，不调用 LibreOffice
- **代码风格反馈**：新增/修改的注释、模块说明和 docstring 使用中文；本轮同步整理新增表格模块的英文说明
- **执行方式**：按 TDD 连续完成 11.1-11.5，完成后停在 Gate 4

#### Step 11：PPTX 文本与媒体解析 [完成 2026-07-18]

##### 产出

- `backend/app/parsers/ppt_convert.py`：`PptxParser`、PPTX 内容校验、分幻灯片文本提取
- `backend/app/parsers/pptx_media.py`：从 `ppt/media/` 提取媒体并生成 Base64 映射
- `backend/app/parsers/__init__.py`：注册 `pptx -> PptxParser`，不注册旧 `.ppt`
- `backend/pyproject.toml`：新增 `python-pptx>=1.0.0`
- `backend/tests/test_parsers/test_ppt_parser.py`：真实内存 PPTX 文本、图片、Registry 与旧格式拒绝测试

##### TDD 与验证

- **RED**：`5 failed`，原因均为 `ppt_convert.py` / `pptx_media.py` 尚不存在
- **GREEN**：PPT 专项 `5 passed`
- **全部 Parser 回归**：`82 passed`
- **Ruff**：本轮新增/修改文件 `All checks passed`
- **历史 Ruff 说明**：全目录仍有 26 个既有类型注解/导入格式问题，本阶段未越界修改

##### 中文注释规范

- 本轮新增的 PPTX/XLS/CSV 模块说明和 docstring 均使用中文
- 本轮涉及的 XLSX 模块英文说明与 TODO 已同步改为中文
- 异常字符串和数据字段保持契约稳定，不因注释语言调整而变化

##### Stage 4 结论

- **Step 10 表格套件**：PASS
- **Step 11 PPTX 套件**：PASS
- **Stage 4**：完成，等待用户回复 `Stage 4 Approved`

#### 2026-07-18 Gate 4 通过与 Stage 5 研究

- **Gate 4 用户指令**：“继续下一阶段”——视为明确批准 Stage 4，进入 Stage 5
- **参考实现结论**：docreader WebParser 包含浏览器抓取、SPA 等待、代理和站点适配，超出本学习任务
- **职责调整**：Stage 5 复用 docreader 的 URL 抓取能力，但拆为 `web_fetcher.py` 与 `web_parser.py`；持久化仍由 SourceAdapter 负责
- **当前门禁**：Step 12 精确 Plan 已落盘，收到 `Plan Approved` 后进入 Execute

#### Step 12：URL、微信文章与 MHTML 解析 [完成 2026-07-18]

##### 产出

- `backend/app/parsers/web_fetcher.py`：公网 URL 校验、浏览器请求拦截、同步 Chromium 抓取、SPA 正文等待
- `backend/app/parsers/web_parser.py`：Trafilatura 正文提取、微信公众号适配、可见文本 fallback、共享 HTML → Markdown 转换
- `backend/app/parsers/mhtml_parser.py`：MIME 主正文选择、广告部件过滤、内嵌图片 Base64 提取和引用重写
- `backend/app/parsers/__init__.py`：注册 `.html/.htm/.mhtml/.mht`
- `backend/pyproject.toml`：新增 Playwright、Trafilatura、BeautifulSoup、markdownify、lxml 生产依赖
- `backend/Dockerfile`：安装 Chromium 及其系统依赖

##### TDD 与验证

- **RED**：`9 failed`，原因均为 `web_fetcher.py`、`web_parser.py`、`mhtml_parser.py` 尚不存在
- **首次 GREEN**：`8 passed, 1 failed`；Trafilatura 2.1 仍过滤微信无扩展名图片
- **契约内修正**：补回微信正文容器内被遗漏的 `mmbiz.qpic.cn?...wx_fmt=` 图片引用
- **网页/MHTML 专项**：`9 passed`
- **全部 Parser 回归**：`91 passed`
- **Ruff**：本阶段新增/修改文件 `All checks passed`
- **受控动态页验收**：Chromium 成功执行延迟 JavaScript，并读取 185 字符渲染后正文
- **真实公网验收**：`https://example.com` 抓取成功，最终 URL、HTML 和可见文本均符合预期

##### 安全边界与偏差

- 初始 URL、每个 HTTP(S) 浏览器请求及最终跳转 URL 均执行公网地址校验，拒绝非 HTTP(S)、localhost、环回、私网、链路本地与保留地址
- 渲染后 HTML 设置 10,000,000 字符学习版上限；导航、networkidle 和正文等待均有超时
- 微信平台登录、验证码、文章删除和风控属于站点边界，不提供绕过能力
- **计划偏差**：无；URL 的 MinIO/数据库持久化仍按计划留给独立 `WebUrlSourceAdapter` Spec

##### Stage 5 结论

- **Step 12**：PASS
- **Stage 5**：完成，停在 Gate 5；未经用户明确批准不进入 Stage 6

#### 2026-07-19 Gate 5 通过与 Stage 6 Plan

- **Gate 5 用户指令**：“进行下一阶段”——明确批准 Stage 5，进入 Stage 6
- **参考实现差异**：docreader 的 EPUBParser 已覆盖章节与图片，但 ImageParser 只返回 Base64，没有实现原 Spec 要求的 Pillow/EXIF
- **Stage 6 决策**：EPUB 复用章节/图片能力并增加 ZIP 资源限制；ImageParser 补齐 Pillow 元数据、EXIF、像素限制和 OCR 状态占位
- **执行方式调整**：用户明确取消 TDD；Stage 6 直接完成实现与测试代码，再统一运行专项和全量回归，不执行逐项 RED→GREEN
- **依赖现状**：本机已有 Pillow，尚未安装 ebooklib；依赖安装在 Execute 13.3 完成
- **Plan Approved**：用户已给出精确审批指令，进入 Execute

#### Step 13：EPUB 与图片解析 [完成 2026-07-19]

##### 产出

- `backend/app/parsers/epub_parser.py`：EPUB ZIP 资源校验、ebooklib 读取、spine 章节排序、Dublin Core 元数据和内嵌图片重写
- `backend/app/parsers/image_parser.py`：Pillow 图片验证、尺寸/模式/EXIF、Base64 映射、像素限制和 OCR 状态占位
- `backend/app/parsers/__init__.py`：注册 `.epub` 和 `.png/.jpg/.jpeg/.gif/.webp/.bmp/.tif/.tiff`
- `backend/pyproject.toml`：新增 `ebooklib>=0.18` 和 `Pillow>=10.0.0`
- `backend/tests/test_parsers/test_epub_parser.py`：真实 EPUB 章节、图片、资源限制、错误和 Registry 测试
- `backend/tests/test_parsers/test_image_parser.py`：真实 JPEG/EXIF、Base64、路径、像素限制、错误和 Registry 测试

##### 实现与验证

- **执行方式**：按用户要求取消 TDD，直接完成实现与测试后统一验证
- **EPUB/图片专项**：`10 passed`
- **全部 Parser 回归**：`101 passed`
- **Ruff**：本阶段新增/修改文件 `All checks passed`
- **diff 检查**：无空白错误，仅有 Windows LF/CRLF 转换提示

##### 安全边界与偏差

- EPUB：最多 10,000 个 ZIP 成员；单成员 32 MB；总解压 128 MB；压缩比最多 100
- 图片：最多 40,000,000 声明像素；超限或无效输入返回 `metadata.error`
- OCR：本阶段不安装 Tesseract 等外部引擎，只输出 `ocr_status=not_configured`
- **计划偏差**：无；执行顺序按用户要求由 TDD 调整为实现后统一测试

##### Stage 6 结论

- **Step 13**：PASS
- **Stage 6**：完成，停在 Gate 6；未经用户明确批准不进入 Stage 7

#### 2026-07-19 Gate 6 通过与 Stage 7 Plan

- **Gate 6 用户指令**：“现在进行下一阶段”——明确批准 Stage 6，进入 Stage 7
- **环境事实**：本机已有 `markitdown`；未安装 `opendataloader-pdf`；Java 17 可用
- **依赖决策**：两个引擎均为 `advanced` 可选依赖，不进入默认生产依赖，不在模块顶层 import
- **实现决策**：不只写 TODO 骨架；实现完整适配器和可用性检查，Stage 8 再接入双 key Registry
- **执行方式**：沿用用户要求，不使用 TDD；实现完成后统一补测试和回归
- **当前门禁**：Stage 7 精确 Plan 已落盘，收到精确 `Plan Approved` 后进入 Execute

#### Step 14：MarkItDown 与 OpenDataLoader 高级引擎适配器 [完成 2026-07-19]

##### 产出

- `backend/app/parsers/markitdown_parser.py`：惰性导入 `markitdown`，使用 `MarkItDown.convert(BytesIO(content), file_extension=..., keep_data_uris=True)` 输出 Markdown
- `backend/app/parsers/opendataloader_parser.py`：检查 Java 11+ 与 `opendataloader_pdf` 包；临时目录调用 `convert()`，读取 Markdown，收集图片 Base64 并重写为 `images/<文件名>`
- `backend/app/parsers/__init__.py`：只导出 `MarkitdownParser` 与 `OpenDataLoaderParser`，不注册默认 file_type
- `backend/pyproject.toml`：新增 `[project.optional-dependencies].advanced`
- `backend/tests/test_parsers/test_markitdown_parser.py` / `test_opendataloader_parser.py`：覆盖可用性、缺依赖、成功、失败、空结果、图片引用重写和临时目录清理

##### 验证

- 高级引擎专项：`pytest tests/test_parsers/test_markitdown_parser.py tests/test_parsers/test_opendataloader_parser.py -q -p no:cacheprovider` → `14 passed`
- Parser 全量回归：`pytest tests/test_parsers -q -p no:cacheprovider` → `115 passed`
- Ruff：`ruff check app/parsers/markitdown_parser.py app/parsers/opendataloader_parser.py app/parsers/__init__.py tests/test_parsers/test_markitdown_parser.py tests/test_parsers/test_opendataloader_parser.py` → `All checks passed`

##### 边界与偏差

- Stage 7 未接入默认 Registry；`.pdf` 仍由内置 `PdfParser` 处理，符合“Stage 8 双 key Registry 后再注册 engine”的计划
- `opendataloader-pdf` 本机未安装，真实转换路径通过 fake module 测试；可用性检查会明确返回 `dependency_unavailable`
- MarkItDown 的 `keep_data_uris=True` 若遇到旧版库不支持该参数，会自动降级重试，避免可选引擎因版本差异直接失败
- **计划偏差**：无

##### Stage 7 结论

- **Step 14**：PASS
- **Stage 7**：完成，停在 Gate 7；未经用户明确批准，不进入 Stage 8

### 2026-07-19 Gate 7 通过与 Stage 8 Plan

- **Gate 7 用户指令**：“继续 下一阶段的任务”——明确批准 Stage 7，进入 Stage 8。
- **当前 phase**：PLAN（LOCKED），未修改任何实现代码。
- **Research 结论**：必须引入 `(engine, file_type)` 双 key，同时保留单参数 builtin 查询和 `KeyError` 契约，避免 Step 20 前破坏 worker 与既有格式测试。
- **Innovate**：跳过；双 key 方向已在原始 Spec 确定，本轮只做兼容迁移设计。
- **File Changes**：`registry.py`、`parsers/__init__.py`、`test_registry.py`，不修改 worker。
- **执行方式**：恢复 TDD；先让新 Registry 契约测试失败，再实现并运行全量 parser 回归。
- **当前门禁**：Stage 8 精确 Plan 已落盘，收到精确 `Plan Approved` 后进入 Execute。
- **Plan Approved**：用户已精确批准 Stage 8 Plan，进入 Execute；严格按 15.1-15.5 执行。
- **代码质量评审首轮**：CHANGES REQUESTED；发现畸形 availability probe 返回值可能中断 `list_engines()`，以及空/规范化重复 key 会形成静默错误配置。以上均属现有“容错枚举 + 注册原子性”契约的边界补强，已先 Reverse Sync 到 §4.2 行为契约，再按 TDD 修复。

### Step 15：Registry 双 key + builtin 兜底 [完成 2026-07-19]

#### 产出

- `backend/app/parsers/registry.py`：`ParserEngineRegistry` 双 key 映射、builtin fallback、单参数兼容入口、原子注册、能力枚举与 availability probe 隔离。
- `backend/app/parsers/__init__.py`：按 engine 注册 builtin 全量格式、MarkItDown 多格式与 OpenDataLoader PDF，并导出 Registry 公共符号。
- `backend/tests/test_parsers/test_registry.py`：覆盖路由、fallback、兼容、规范化、原子性、能力列表、畸形探针与全局默认映射。

#### TDD 与验证

- **第一轮 RED**：`14 failed`；旧单 key Registry 缺少 mapping 注册、双 key 查询、引擎枚举和元数据 API。
- **第一轮 GREEN**：Registry 专项 `14 passed`；Parser 全量 `117 passed`；Ruff 通过。
- **质量评审首轮**：Spec 合规 PASS；代码质量 CHANGES REQUESTED（畸形 probe、空 key、规范化重复 key）。
- **第二轮 RED**：`6 failed, 14 passed`；准确复现两项质量问题及注册状态原子性边界。
- **最终 GREEN**：Registry 专项 `20 passed`；Parser 全量 `123 passed`；Ruff `All checks passed`；`git diff --check` 无空白错误，仅 Windows LF/CRLF 提示。
- **独立质量复审**：Critical / Important / Minor 均为 None，Assessment `Approved`。

#### 教学要点回顾

- 双 key Registry 把“解析引擎选择”和“文件格式选择”分成两个正交维度，同一格式可以挂多个实现。
- builtin fallback 保证高级引擎未知或不支持某格式时仍可回到稳定内置实现；单参数入口让迁移分阶段完成。
- 原子注册必须先完整规范化与校验，再一次性替换状态；能力探针属于不可信边界，其异常和畸形返回都不能击穿能力列表。

#### 偏差说明

- **计划内边界补强**：质量评审发现的畸形 probe 与非法 key 行为已先 Reverse Sync 到行为契约，再按 TDD 修复。
- **范围偏差**：无；实现只修改计划中的 3 个文件，worker 显式 engine 接入仍留在 Step 20。

#### Stage 8 首轮最终 Review 反馈

- **Axis 1**：PASS。
- **Axis 2 / Axis 3**：PARTIAL；`list_engines()` 会执行人为注册给 builtin 的 availability probe，可能返回 `available=False`，违反 §4.2 “builtin 永远视为可用”契约。
- **Overall Verdict**：FAIL；Gate 8 暂不通过。
- **修正动作**：按原契约先补失败测试，强制 builtin 跳过 probe 并始终输出 `available=True / unavailable_reason=""`，再执行全量验证与 Review。
- **缺陷修正 RED/GREEN**：新增 builtin probe 不执行测试后先失败；修复后 Registry 专项 `22 passed`，Parser 全量 `125 passed`，Ruff 通过。
- **最终复审**：Axis 2 PASS / Axis 3 PASS / Blocking Issues 无 / Overall Verdict PASS。

### 2026-07-19 Gate 8 通过与 Stage 9-11 批量收尾

- **用户指令**：“现在看下进行到哪个阶段了 接下来把所有阶段都完成，然后给我 summarize”。
- **授权解释**：视为 Gate 8-11 连续推进授权；本轮一次完成 Stage 9/10/11 并做最终 Review。
- **执行方式**：沿用“下次不用 TDD”决策——先实现后补测，最后统一回归。

### Stage 9：Markdown utils（Step 16-17）[完成 2026-07-19]

#### 产出

- `backend/app/parsers/_utils/endecode.py`：补齐 `encode_image(base64 → bytes)`。
- `backend/app/parsers/markdown_parser.py`：
  - `MarkdownTableUtil` / `MarkdownTableFormatter`
  - `MarkdownImageUtil` / `MarkdownImageBase64`
- `backend/tests/test_parsers/test_markdown_parser.py`：重写为表格 + base64 契约测试。

#### 验证

- 歪斜表格可标准化为 GFM 间距/对齐。
- MarkItDown 伪前缀空行/分隔行可清理并补 delimiter。
- `data:image/...;base64,...` 可抽取为 `images/<uuid>.ext`，正文替换为路径引用。

#### 教学要点

- 表格规范化属于“内容整形”，应在 markdown 层统一做，而不是每个上游 parser 各写一份。
- Base64 图片抽取把“内嵌二进制”变成“路径引用 + images dict”，方便后续存储/上传解耦。

### Stage 10：ChainParser（Step 18-19）[完成 2026-07-19]

#### 产出

- `backend/app/parsers/chain.py`：`FirstParser` + `PipelineParser` + `create()` 动态子类工厂。
- `MarkdownParser(PipelineParser)`：`_parser_cls = (MarkdownTableFormatter, MarkdownImageBase64)`。
- `backend/tests/test_parsers/test_chain.py`：责任链失败跳过、管道内容串接、images/metadata 合并。

#### 验证

- `FirstParser.create(Fail, Raise, Ok)` 返回 Ok。
- `PipelineParser.create(Prefix, Suffix)` 输出 `A:raw:B`，images/metadata 合并。
- Markdown 同时含表格与 base64 图片时，两阶段都生效。

#### 教学要点

- FirstParser = 责任链（谁先成功用谁）；PipelineParser = 管道（前输出喂后输入）。
- `type(name, bases, dict)` 动态生成子类，把“组合配置”从实例参数提升到类型身份，便于 Registry 注册。
- 渐进式抽象闭环：Step 7 最简 Markdown → Step 19 管道组合，对比出“胖 parser 拆阶段”的价值。

### Stage 11：测试 + 收尾（Step 20）[完成 2026-07-19]

#### 产出

- 新增 `backend/app/parsers/dispatch.py`：`parse_to_text(filename, raw_bytes, engine=None)`。
- `backend/app/workers/parse_document.py`：改为调用 `dispatch.parse_to_text`。
- `backend/app/parsers/__init__.py`：导出 `FirstParser` / `PipelineParser` / Markdown 阶段类。
- `backend/tests/test_parsers/test_parse_document_dispatch.py`：默认 builtin、显式 engine、未知扩展名兜底。

#### 验证

- `pytest tests/test_parsers/` → **130 passed, 1 skipped**。
- 可选高级引擎缺依赖时仍 skip，不影响主路径。
- `test_document.py` 仍是依赖 docker/worker 的集成测试，不在本轮单测门禁内强制执行。

#### 偏差说明

- **计划内增强**：把 `_parse_to_text` 从 worker 抽到 `parsers/dispatch.py`。原因：直接 import worker 会初始化 SQLAlchemy async engine，单测环境无 DSN 会 collection fail。
- **范围未扩散**：未改上传 API、未改 DB schema、未做 URL 持久化 SourceAdapter。

---

## §6 Review Verdict

### Stage 7 Review（2026-07-19）

| 评审轴 | 结论 | 证据 |
|---|---|---|
| Spec 质量与目标达成 | PASS | Step 14 契约明确覆盖两个可选高级引擎、依赖策略、错误返回和 Registry 边界 |
| Spec-Code 一致性 | PASS | 实现文件、导出、可选依赖和测试均与 Step 14 checklist 对齐；未注册默认 file_type |
| 代码自身质量 | PASS | `14 passed` 专项、`115 passed` parser 回归、Ruff 通过；缺依赖和转换失败均返回 `metadata.error` |

- **Overall Verdict**：PASS
- **Blocking Issues**：无

### Stage 8 Review（2026-07-19）

| 评审轴 | 结论 | 证据 |
|---|---|---|
| Spec 质量与目标达成 | PASS | Stage 8 Research、精确签名、三文件范围、行为契约和 Step 15 checklist 完整；双 key Registry 与能力枚举目标已达成 |
| Spec-Code 一致性 | PASS | `ParserEngineRegistry`、兼容别名、builtin fallback、三种默认 engine、原子注册、探针隔离均与 §4.2 一致；builtin 永远可用缺陷已补测修复 |
| 代码自身质量 | PASS | Registry `22 passed`、全部 Parser `125 passed`、Ruff 通过；独立质量复审无 Critical/Important/Minor 问题，最终复审无阻塞 |

- **Overall Verdict**：PASS
- **Blocking Issues**：无
- **Gate 8**：已由用户“把所有阶段都完成”批量推进授权覆盖（2026-07-19）。

### 后续执行方式决策（2026-07-19）

- **用户指令**：“下次不用TDD了”。
- **适用范围**：本 Spec 后续 Stage 9-11。
- **执行方式**：不再要求先写失败测试或展示 RED；先按已批准 Plan 完成实现，再统一补充/调整测试并运行专项与全量回归。
- **缺陷处理**：发现缺陷时仍必须增加对应回归测试，防止同类问题再次出现，但不强制采用 RED → GREEN 顺序。
- **批量收尾授权**：用户指令“接下来把所有阶段都完成”（2026-07-19），Gate 8-11 连续推进并完成最终 Review。

### Stage 9-11 Final Review（2026-07-19）

| 评审轴 | 结论 | 证据 |
|---|---|---|
| Spec 质量与目标达成 | PASS | Step 16-20 checklist 全部完成；验收标准中的核心抽象、utils、parser、测试、worker 接入均已落地 |
| Spec-Code 一致性 | PASS | Markdown utils / Chain / Pipeline MarkdownParser / dispatch engine 参数均与 §4.1-§4.3 对齐；旧最简 Markdown 与 Text 等价测试已按计划删除 |
| 代码自身质量 | PASS | `pytest tests/test_parsers/` → `130 passed, 1 skipped`；派发逻辑抽离避免测试依赖 DB；可选高级引擎仍 skip |

- **Overall Verdict**：PASS
- **Blocking Issues**：无
- **Task Status**：COMPLETE

---

## §7 Plan-Execution Diff

### Stage 8

- **File Changes**：无偏差，仅修改 `registry.py`、`parsers/__init__.py`、`test_registry.py`。
- **Signatures**：无偏差，计划中的 Registry 公共 API 与兼容别名均已实现。
- **Behavior**：最终无偏差；评审中发现的 malformed probe、非法 key、builtin availability 边界均先同步契约或按原契约补测修复。
- **Deferred Scope**：worker 显式 engine 参数仍按计划留在 Step 20。

### Stage 9-11

- **File Changes**：
  - 计划内：`markdown_parser.py`、`chain.py`、`endecode.py`、`__init__.py`、相关测试、`parse_document.py` engine 接入。
  - 额外新增：`parsers/dispatch.py`（把派发逻辑从 worker 抽离，避免单测 import worker 时创建 DB engine）。
- **Signatures**：`parse_to_text(filename, raw_bytes, engine=None)` 成为公开派发入口；worker 继续调用兼容别名 `_parse_to_text`。
- **Behavior**：MarkdownParser 从“最简 decode”升级为 `PipelineParser(MarkdownTableFormatter, MarkdownImageBase64)`；不再与 TextParser 行为等价。
- **Test Strategy**：按用户决策不做强制 TDD 顺序；实现后统一补测试并全量回归。
