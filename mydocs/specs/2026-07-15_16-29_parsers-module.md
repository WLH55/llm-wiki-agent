# SDD Spec: backend/app/parsers 文档解析模块（参考 docreader 移植）

## RIPER 状态

- **phase**: EXECUTE（Stage 4 进行中）
- **approval status**: APPROVED（Stage 1 ✅ / Stage 2 ✅ 2026-07-16 / Stage 3 ✅ 2026-07-17）
- **execute status**: Stage 1 ✅ / Stage 2 ✅ / Stage 3 ✅ / Stage 4 Step 10 进行中
- **review status**: 未开始
- **spec path**: `mydocs/specs/2026-07-15_16-29_parsers-module.md`
- **active project**: llm_wiki3.0（单项目）
- **change scope**: local（仅改 `backend/app/parsers/` + `backend/tests/test_parsers/` + `backend/pyproject.toml`）
- **current stage**: Stage 4（Office 套件，Step 10-11）进行中
- **current step**: Step 10（Excel 套件）
- **next**: 按 TDD 完成 Step 10 并验证 → 停在 Step 11 前等待单步继续指令

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

- [ ] **Q8：高级引擎（MarkitDown / OpenDataLoader）的外部依赖怎么处理？**
  - MarkitdownParser 需微软 `markitdown` 库；OpenDataLoaderParser 需 `opendataloader-pdf` + Java 11+
  - **推荐：B（按需安装）**——不预装，留 TODO；Plan 阶段写到这两个 parser 时再决策

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
| Excel 套件 | `excel_parser.py` + `excel_convert.py` + `xlsx_merge.py` + `xlsx_repair.py` | docreader 原版 | openpyxl |
| PPT 套件 | `ppt_convert.py` + `pptx_media.py` | docreader 原版 | python-pptx |
| 网页 | `web_parser.py` | docreader 原版 | requests + beautifulsoup4 |
| 邮件 | `mhtml_parser.py` | docreader 原版 | 标准库 |
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

### 验收标准

1. `backend/app/parsers/` 目录建好，含 4 核心抽象 + 1 utils + 17 parser = **~22 个文件**
2. `backend/app/workers/parsers.py` **已删除**
3. `backend/app/workers/parse_document.py` 改为 `from app.parsers import registry`
4. `tests/test_parsers/` 下每 parser 一个 happy-path 测试，全部通过
5. 已有的 `tests/test_document.py` 回归测试仍通过
6. 用户能口述清楚：BaseParser / Registry / ChainParser 三大抽象的设计动机
7. 用户能独立加一个新 parser（如 HTMLParser）而不改 Registry 代码（开闭原则验证）
8. 用户能口述 17 种格式各自的解析技术要点

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

---

## §2.1 Next Actions

> §0 Open Questions 已全部决策（Q1-Q7 完成，Q8 待 Plan 阶段到高级引擎时再决），进入 Plan 阶段。

1. **【当前】进入 Plan 阶段**：
   - §4.1 File Changes（明确 22 个文件的产出顺序，按"学习路径"分组）
   - §4.2 Signatures（BaseParser / Registry / ChainParser 的 Python 签名）
   - §4.3 Implementation Checklist（拆 ~15-20 个学习步骤，每步标注"教学要点"）
   - §4.4 Spec Review Notes（自评）

2. **Plan 完成后，等用户 `Plan Approved`**

3. **收到批准后，进入 Execute 阶段**：按 checklist 实施，每步教学 + 编码 + 验证

4. **Execute 完成后，进入 Review 阶段**：三轴评审（spec 一致性 / 代码质量 / 学习目标达成）

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

- **Selected**：**Plan 阶段写代码骨架 + 标 TODO，不预装外部依赖**
- **Why**：markitdown（微软库）和 opendataloader-pdf（需 Java 11+）是重依赖，预装会拖慢学习节奏；用户真正要用时再 `pip install`
- **Avoided**：直接跳过这两个（违背"完美复刻"原则）

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
├── excel_parser.py                       # Excel 主入口
├── excel_convert.py                      # Excel 辅助：格式转换
├── xlsx_merge.py                         # Excel 辅助：多 sheet 合并
├── xlsx_repair.py                        # Excel 辅助：损坏文件修复
├── ppt_convert.py                        # PPT 辅助：格式转换
├── pptx_media.py                         # PPT 辅助：媒体文件抽取
├── web_parser.py                         # 网页（requests + bs4）
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
├── test_ppt_parser.py
├── test_web_parser.py
├── test_mhtml_parser.py
├── test_epub_parser.py
├── test_image_parser.py
├── test_markitdown_parser.py             # skip if 依赖未装
└── test_opendataloader_parser.py         # skip if 依赖未装
```

**总计**：~22 个 parser 模块文件 + 16 个测试文件

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
    def __init__(self):
        self._engines: Dict[str, Dict[str, Type[BaseParser]]] = {}
        self._descriptions: Dict[str, str] = {}

    def register(self, engine: str, file_types: Dict[str, Type[BaseParser]],
                 description: str = "") -> None: ...
    def get_parser_class(self, engine: str, file_type: str) -> Type[BaseParser]:
        """先按 engine 查；engine 不支持该 file_type 时回退 builtin"""
    def list_engines(self) -> List[Dict]: ...
```

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

- [ ] **Step 10：Excel 套件（4 文件）**
  - 教学：openpyxl 多 sheet 遍历；excel_convert 格式转换；xlsx_merge 合并；xlsx_repair 损坏文件修复
  - 产出：`excel_parser.py` + `excel_convert.py` + `xlsx_merge.py` + `xlsx_repair.py`
  - 验证：`.xlsx` 多 sheet → markdown 表格拼接

- [ ] **Step 11：PPT 套件（2 文件）**
  - 教学：python-pptx 遍历 slides/shapes；pptx_media 抽取图片/视频
  - 产出：`ppt_convert.py` + `pptx_media.py`
  - 验证：`.pptx` → 幻灯片文本 + 媒体路径

#### 阶段 5：网页与邮件（Step 12）

- [ ] **Step 12：WebParser + MHTMLParser**
  - 教学：requests + BeautifulSoup 解析 HTML；MHTML 用标准库 email.message_from_string
  - 产出：`web_parser.py` + `mhtml_parser.py`
  - 验证：HTML 字符串 → 纯文本 + 链接；`.mht` → HTML 部分

#### 阶段 6：富文档（Step 13）

- [ ] **Step 13：EPUBParser + ImageParser**
  - 教学：ebooklib 遍历 spine；Pillow 抽取 EXIF + 简单 OCR 占位
  - 产出：`epub_parser.py` + `image_parser.py`
  - 验证：`.epub` → 章节文本；`.jpg` → metadata dict

#### 阶段 7：高级引擎（Step 14）

- [ ] **Step 14：MarkitdownParser + OpenDataLoaderParser**
  - 教学：高级引擎抽象；外部依赖按需安装策略；`check_available` 函数
  - 产出：`markitdown_parser.py` + `opendataloader_parser.py`（代码骨架 + TODO）
  - 验证：依赖未装时 `pytest.skip`；装上后通过

#### 阶段 8：注册表升级（Step 15）

- [ ] **Step 15：Registry 双 key + builtin 兜底**
  - 教学：嵌套字典 `Dict[engine, Dict[file_type, parser]]`；fallback 到 builtin；`list_engines` 列举能力
  - 产出：升级 `backend/app/parsers/registry.py`
  - 验证：`get_parser_class("markitdown", "pdf")` → MarkitdownParser；`get_parser_class("unknown", "pdf")` → builtin PDFParser

#### 阶段 9：Markdown utils（Step 16-17）

- [ ] **Step 16：MarkdownTableFormatter**
  - 教学：GFM 表格规范；正则标准化对齐 + 间距；处理 MarkItDown 的伪前缀行
  - 产出：`markdown_parser.py` 加 `MarkdownTableUtil` + `MarkdownTableFormatter`
  - 验证：歪斜表格 → 标准 GFM

- [ ] **Step 17：MarkdownImageBase64**
  - 教学：Base64 图片抽取；`data:image/png;base64,...` 解析；生成 UUID 文件名
  - 产出：`markdown_parser.py` 加 `MarkdownImageUtil` + `MarkdownImageBase64`
  - 验证：含 base64 的 markdown → 文本 + images dict

#### 阶段 10：ChainParser（Step 18-19）

- [ ] **Step 18：FirstParser + PipelineParser**
  - 教学：责任链 vs 管道的区别；`type()` 动态生成子类（工厂方法）
  - 产出：`backend/app/parsers/chain.py` + `tests/test_parsers/test_chain.py`
  - 验证：`FirstParser.create(A, B)` try A 失败 try B；`PipelineParser.create(A, B)` A 输出喂 B

- [ ] **Step 19：MarkdownParser 升级为 PipelineParser**
  - 教学：组合模式价值——把胖 parser 拆成阶段用管道串起来
  - 产出：升级 `markdown_parser.py` 为 `PipelineParser(TableFormatter, ImageBase64)`
  - 验证：含表格 + base64 的 markdown → 标准化 + 抽取

#### 阶段 11：测试 + 收尾（Step 20）

- [ ] **Step 20：完整测试 + 接入验证**
  - 教学：契约测试 vs 实现测试；skip 装饰器处理可选依赖
  - 产出：补全 `tests/test_parsers/test_*.py`；改 `parse_document.py` 支持指定 engine
  - 验证：`pytest tests/test_parsers/` 全过；`pytest tests/test_document.py` 回归通过

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

---

## §6 Review Verdict

> 待 Review 阶段填充。
