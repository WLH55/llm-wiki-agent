# BaseParser + Registry 设计模式

> 来源：docreader 模块（`docreader/parser/`）的解析框架抽象。本文用教学视角拆解这个模式是什么、为什么这样设计、如何扩展、以及它对应哪些经典设计模式。
>
> 真实代码引用：
> - 抽象基类：`docreader/parser/base_parser.py`
> - 注册表：`docreader/parser/registry.py`
> - 组合基类：`docreader/parser/chain_parser.py`
> - 数据契约：`docreader/models/document.py`

---

## 0. TL;DR（一句话）

**BaseParser + Registry = 把"根据文件类型选解析器"这件事从一堆 `if-elif` 变成"每个 parser 自己注册自己，调用方按 key 查表派发"**。再叠加 Pipeline/First 组合模式，就能用一行 `_parser_cls = (A, B)` 表达"先试 A 再试 B"或"A 的输出喂给 B"。

---

## 1. 为什么需要这个模式

### 1.1 反例：if-elif 链（最常见的初版写法）

```python
def parse(file_name: str, content: bytes) -> str:
    name = file_name.lower()
    if name.endswith(".pdf"):
        return parse_pdf(content)
    elif name.endswith(".docx"):
        return parse_docx(content)
    elif name.endswith(".md"):
        return parse_markdown(content)
    elif name.endswith(".xlsx"):
        return parse_excel(content)
    # ... 20 行后维护噩梦
    else:
        return content.decode("utf-8", errors="replace")
```

我们项目当前 `backend/app/workers/parsers.py` 就是这个写法。它有 4 个分支还能忍，加到 20 个分支时会出三个问题：

| 问题 | 表现 |
|---|---|
| **加格式要改核心函数** | 加 EPUB 支持要回去改 `parse()` 函数体，违反开闭原则 |
| **同一个格式多实现没法共存** | PDF 有 pdfplumber / pdfium / MinerU 三种实现，怎么让用户选？if-elif 表达不了"按引擎选" |
| **无法在运行时列举能力** | 客户端问"你支持哪些格式？"——只能硬编码另一个列表，和上面的 if-elif 双份维护 |

### 1.2 反例：简单工厂（半成品改进）

```python
PARSERS = {
    "pdf": PDFParser,
    "docx": DocxParser,
    "md": MarkdownParser,
}

def parse(file_type: str, content: bytes) -> str:
    cls = PARSERS.get(file_type)
    return cls().parse(content) if cls else ""
```

进步：把"选 parser"从 if-elif 改成了字典查找。但仍然缺三件事：

1. 字典是**全局可变状态**，任何模块都能改，没封装
2. 没法表达"双层 key"（engine + file_type）
3. 没法表达"找不到时回退到默认引擎"

### 1.3 正解：BaseParser + Registry

把"选 parser"这件事**封装成一个独立对象** `ParserRegistry`，给它提供 `register / get / list` 三个方法。再定义一个抽象基类 `BaseParser` 约束所有 parser 的接口形状。完成。

---

## 2. 三大角色

### 2.1 BaseParser（抽象基类 / 接口契约）

`docreader/parser/base_parser.py`：

```python
from abc import ABC, abstractmethod
from docreader.models.document import Document

class BaseParser(ABC):
    """所有 parser 的抽象基类"""

    def __init__(self, file_name: str = "", file_type: str | None = None, **kwargs):
        self.file_name = file_name
        self.file_type = file_type or os.path.splitext(file_name)[1].lstrip(".")

    @abstractmethod
    def parse_into_text(self, content: bytes) -> Document:
        """子类必须实现：把 raw bytes 解析成 Document"""

    def parse(self, content: bytes) -> Document:
        """模板方法：日志 + 调用 parse_into_text"""
        logger.info("Parsing document with %s, bytes: %d", self.__class__.__name__, len(content))
        document = self.parse_into_text(content)
        logger.info("Extracted %d characters", len(document.content))
        return document
```

**两个关键设计点**：

#### (1) 模板方法（Template Method）

`parse()` 是非抽象的，子类只实现 `parse_into_text()`。这样：
- 子类**不需要**自己写日志、计时、异常包装
- 框架能在 `parse()` 里统一加 cross-cutting concerns（监控、tracing、限流等）
- 子类的职责被压缩到"纯解析逻辑"

#### (2) Document 作为统一输出契约

`docreader/models/document.py`：

```python
class Document(BaseModel):
    content: str                    # markdown 文本
    images: Dict[str, str] = {}     # 路径 → base64
    chunks: List[Chunk] = []        # （docreader 不用，留给外部）
    metadata: Dict[str, Any] = {}   # 任意元信息（页数、标题、作者…）
```

**所有 parser 都返回同一种类型**——调用方不需要知道是 PDF 还是 EPUB，统一处理 `Document.content` 即可。这是 Strategy 模式能成立的前提：**接口形状必须一致**。

---

### 2.2 ParserRegistry（注册表）

`docreader/parser/registry.py` 节选：

```python
class ParserEngineRegistry:
    """每个引擎是 {file_type → parser_cls} 的映射；引擎之间互相独立"""

    def __init__(self):
        self._engines: Dict[str, Dict[str, Type[BaseParser]]] = {}
        self._descriptions: Dict[str, str] = {}
        self._check_available: Dict[str, Callable] = {}

    def register(self, name, file_types: Dict[str, Type[BaseParser]],
                 description="", check_available=None):
        """注册一个引擎：name 是引擎名，file_types 是 {ext: ParserCls}"""
        self._engines[name] = file_types
        self._descriptions[name] = description
        if check_available:
            self._check_available[name] = check_available

    def get_parser_class(self, engine: str, file_type: str) -> Type[BaseParser]:
        """双层 key 派发：先查 (engine, file_type)，查不到回退 builtin"""
        ft = file_type.lower()
        if engine and engine in self._engines:
            cls = self._engines[engine].get(ft)
            if cls:
                return cls
            # 用户指定的引擎不支持这种格式 → 回退 builtin
        builtin = self._engines.get("builtin", {})
        cls = builtin.get(ft)
        if cls:
            return cls
        raise ValueError(f"Unsupported file type: {file_type}")

    def list_engines(self, overrides=None) -> List[Dict]:
        """能力发现：列出所有引擎 + 它们支持的格式 + 是否可用"""
        ...
```

**三个核心能力**：

| 方法 | 解决什么问题 |
|---|---|
| `register(name, file_types)` | **开闭原则**：加引擎/格式不改派发逻辑 |
| `get_parser_class(engine, file_type)` | **双层 key 派发**：用户选 engine（markitdown vs builtin），框架选 file_type |
| `list_engines()` | **运行时能力发现**：客户端能问"你支持什么"，不需要文档对齐 |

#### 注册表初始化（一次性、模块加载时跑）

```python
def _build_default_registry() -> ParserEngineRegistry:
    reg = ParserEngineRegistry()

    reg.register("builtin", {
        "docx": Docx2Parser,
        "doc": DocParser,
        "pdf": PDFParser,
        "md": MarkdownParser,
        "xlsx": ExcelParser,
        "epub": EPUBParser,
        # ...
    }, description="内置解析引擎")

    reg.register("markitdown", {
        "pdf": MarkitdownParser,
        "docx": MarkitdownParser,
        # ...
    }, description="MarkItDown 引擎（微软）")

    reg.register("opendataloader", {"pdf": OpenDataLoaderParser},
                 description="OpenDataLoader（版面分析，需 Java）",
                 check_available=lambda _: opendataloader_available())

    return reg

registry = _build_default_registry()  # 模块级单例
```

#### 调用方使用方式（`docreader/parser/parser.py`）

```python
class Parser:
    def __init__(self):
        self.registry = registry  # 拿到单例

    def parse_file(self, file_name, file_type, content, parser_engine=None):
        cls = self.registry.get_parser_class(parser_engine or "", file_type)
        parser = cls(file_name=file_name, file_type=file_type)
        return parser.parse(content)
```

**调用方完全不知道有哪些格式、有哪些引擎**——只调 `get_parser_class(engine, file_type)`。这就是 Registry 模式的价值：**把"知识"从调用方搬到注册表**。

---

### 2.3 Composite Parser（组合模式）

光有 BaseParser + Registry 还差一块：**怎么表达"先试 A，A 失败再试 B"或"A 的输出喂给 B 再加工"**？

答案：再写两个特殊的 BaseParser 子类，它们**不解析具体格式，而是组合其他 parser**。这就是 Composite 模式。

`docreader/parser/chain_parser.py`：

#### FirstParser（短路 / 备胎链）

```python
class FirstParser(BaseParser):
    """按顺序试每个 parser，第一个返回有效结果的胜出"""
    _parser_cls: Tuple[Type[BaseParser], ...] = ()

    def parse_into_text(self, content: bytes) -> Document:
        for p in self._parsers:
            try:
                document = p.parse_into_text(content)
                if document.is_valid():
                    return document
            except Exception:
                continue  # 这个 parser 挂了，试下一个
        return Document()  # 全军覆没
```

**真实用例** `docreader/parser/docx2_parser.py`：

```python
class Docx2Parser(FirstParser):
    _parser_cls = (MarkitdownParser, DocxParser)
    # 先试 MarkItDown（解析更完整），失败回退到 python-docx
```

这就是"声明式组合"——一行 `_parser_cls = (A, B)` 替代了一堆 if-else 异常处理。

#### PipelineParser（串联 / 流水线）

```python
class PipelineParser(BaseParser):
    """每个 parser 的输出是下一个 parser 的输入；图片元数据合并"""
    _parser_cls: Tuple[Type[BaseParser], ...] = ()

    def parse_into_text(self, content: bytes) -> Document:
        images, metadata = {}, {}
        document = Document()
        for p in self._parsers:
            document = p.parse_into_text(content)
            content = encode_bytes(document.content)  # 输出转回 bytes 喂给下一个
            images.update(document.images)
            metadata.update(document.metadata)
        document.images.update(images)
        document.metadata.update(metadata)
        return document
```

**真实用例 1** `docreader/parser/markdown_parser.py`：

```python
class MarkdownParser(PipelineParser):
    _parser_cls = (MarkdownTableFormatter, MarkdownImageBase64)
    # 第 1 步：规范化表格格式
    # 第 2 步：抽出 base64 图片
```

**真实用例 2** `docreader/parser/markitdown_parser.py`：

```python
class MarkitdownParser(PipelineParser):
    _parser_cls = (StdMarkitdownParser, MarkdownParser)
    # 第 1 步：MarkItDown 把 docx/pdf/pptx 转成 markdown
    # 第 2 步：复用 MarkdownParser 处理表格 + 抽 base64 图片
```

#### 组合模式的关键特性

> **Pipeline 和 First 自身也是 BaseParser 子类**——它们可以被注册到 Registry，也可以被嵌套进另一个 Pipeline/First。

这意味着你可以无限嵌套：

```python
class UltimateDocxParser(FirstParser):
    # 三个备胎链，每个备胎链自己又是一个 pipeline
    _parser_cls = (
        PipelineParser.create(MineruParser, MarkdownCleaner),
        PipelineParser.create(MarkitdownParser, MarkdownCleaner),
        DocxParser,  # 兜底
    )
```

调用方代码完全不变：`parser.parse(content)`。组合的复杂性被**封在声明里**。

---

## 3. 工作流程（调用时序）

以"用户上传 my.docx，指定 engine=builtin"为例：

```
┌─────────────────────────────────────────────────────────────┐
│ main.py DocReaderServicer.Read(request)                     │
│   ↓                                                          │
│ Parser.parse_file("my.docx", "docx", bytes, "builtin")      │
│   ↓                                                          │
│ registry.get_parser_class("builtin", "docx")                │
│   ↓ 查表                                                     │
│ 返回 Docx2Parser 类                                          │
│   ↓                                                          │
│ Docx2Parser().parse(bytes)                                   │
│   ↓ 走模板方法 BaseParser.parse()                            │
│ Docx2Parser.parse_into_text(bytes)                           │
│   ↓ FirstParser 逻辑：按顺序试                                │
│   ├─ MarkitdownParser.parse_into_text(bytes)                 │
│   │    ↓ PipelineParser 逻辑：串联                            │
│   │    ├─ StdMarkitdownParser: docx → markdown               │
│   │    └─ MarkdownParser:                                     │
│   │         ├─ MarkdownTableFormatter: 规范化表格             │
│   │         └─ MarkdownImageBase64: 抽 base64 图片            │
│   │    ↓ 返回 Document                                        │
│   │  ✓ 成功 → 直接返回                                        │
│   └─ （DocxParser 没机会跑）                                  │
│   ↓                                                          │
│ 返回 Document{content, images, metadata}                     │
└─────────────────────────────────────────────────────────────┘
```

**关键观察**：调用方只看到 `parser.parse(bytes) → Document`，内部走了 4 层嵌套（First → Pipeline → Std → Pipeline → Formatter）。复杂度被吃掉了。

---

## 4. 实战：加一种新格式

需求：支持 `.epub` 电子书，用 `ebooklib` 解析。

### 步骤 1：写具体 parser（继承 BaseParser）

```python
# docreader/parser/epub_parser.py
import ebooklib
from docreader.models.document import Document
from docreader.parser.base_parser import BaseParser

class EPUBParser(BaseParser):
    """EPUB → markdown：抽取章节文本 + 内嵌图片"""

    def parse_into_text(self, content: bytes) -> Document:
        book = ebooklib.epub.read_epub(BytesIO(content))
        parts = []
        images = {}
        for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
            html = item.get_content().decode("utf-8", errors="replace")
            parts.append(html_to_markdown(html))
        for item in book.get_items_of_type(ebooklib.ITEM_IMAGE):
            images[item.file_name] = base64.b64encode(item.get_content()).decode()
        return Document(content="\n\n".join(parts), images=images)
```

### 步骤 2：注册（只改一处）

```python
# docreader/parser/registry.py
from docreader.parser.epub_parser import EPUBParser

reg.register("builtin", {
    ...,
    "epub": EPUBParser,  # ← 加这一行
})
```

### 步骤 3：完事

调用方代码 **零改动**。`registry.get_parser_class("builtin", "epub")` 自动找到新 parser。

**对比 if-elif 写法**：要改 `parse()` 函数体 + 加 `import` + 也许还要改 `list_supported_formats()`。三处改动，且其中两处容易忘。

---

## 5. 设计模式本质

这个看似简单的架构实际叠加了 **4 个经典设计模式**：

| 模式 | 体现在哪 | 解决什么 |
|---|---|---|
| **Strategy（策略）** | BaseParser + 各种子类 | 同一接口、不同实现可互换 |
| **Registry（注册表）** | `ParserEngineRegistry` | 把"选谁"的知识从调用方搬到独立对象 |
| **Template Method（模板方法）** | `BaseParser.parse()` 调 `parse_into_text()` | 公共流程（日志、计时）下沉到基类 |
| **Composite（组合）** | `FirstParser` / `PipelineParser` 也是 BaseParser | 用声明式拼接表达"备胎链"和"流水线"，且可无限嵌套 |

### 与工厂模式的区别

新手常把它叫"工厂模式"，但严格来说**不是**：

- **工厂模式**：`ParserFactory.create(file_type)` —— 调用方知道工厂存在，工厂**封装**创建逻辑
- **Registry 模式**：parser **自注册**到 registry，调用方只知道 registry —— 解耦更彻底，加 parser 不需要改 factory

### 与插件模式的区别

- **插件模式**：在 Registry 基础上**支持运行时加载**（如 `pkgutil.iter_modules` 动态发现）
- **docreader 的 Registry**：注册在 `_build_default_registry()` 静态函数里，**编译期**确定

如果要做成"用户放一个 `my_format_parser.py` 进 plugins/ 目录就自动被发现"——在 Registry 之上叠一层 entry_point / pkgutil 扫描即可，**不需要改 BaseParser**。

---

## 6. docreader 支持的所有文档格式

按 `docreader/parser/registry.py` 的实际注册情况整理。

### 6.1 builtin 引擎（默认）

| 类别 | 扩展名 | Parser | 备注 |
|---|---|---|---|
| 文档 | `.pdf` | `PDFParser` | 内置版面分析（扫描页 vs 文字页路由） |
| 文档 | `.docx` | `Docx2Parser` | FirstParser：先 markitdown，失败回退 python-docx |
| 文档 | `.doc` | `DocParser` | 老 Word 格式 |
| 文档 | `.epub` | `EPUBParser` | 电子书 |
| 文档 | `.mhtml` | `MHTMLParser` | 单文件网页归档 |
| 文本 | `.md`, `.markdown` | `MarkdownParser` | Pipeline：表格规范化 + base64 图片抽取 |
| 表格 | `.xlsx`, `.xls` | `ExcelParser` | 多 sheet 合并 |
| 图片 | `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tiff`, `.webp` | `ImageParser` | 不做 OCR，直接转 markdown 引用 |

### 6.2 markitdown 引擎（可选）

| 类别 | 扩展名 | 备注 |
|---|---|---|
| 文档 | `.pdf`, `.docx`, `.doc` | 微软 MarkItDown 库 |
| 演示 | `.pptx`, `.ppt` | ppt 先 normalize 成 pptx，再走 markitdown |
| 表格 | `.xlsx`, `.xls`, `.csv` | CSV 也能处理 |
| 文本 | `.md`, `.markdown` | 用 markitdown 走一遍 |

### 6.3 opendataloader 引擎（可选，需 Java 11+）

| 类别 | 扩展名 | 备注 |
|---|---|---|
| 文档 | `.pdf` | OpenDataLoader，做版面分析，强项是复杂表格 |

### 6.4 特殊：URL（不进 Registry）

`docreader/parser/parser.py` 的 `parse_url()` 直接 `WebParser(title=title).parse(url_bytes)`——网页走单独路径，不在 file_type 注册表里。

### 6.5 总览（去重）

```
PDF       .pdf               （3 引擎可选）
Word      .doc, .docx
Excel     .xls, .xlsx, .csv
PowerPoint .ppt, .pptx
Ebook     .epub
Web       .mhtml, 任意 URL
Text      .md, .markdown
Image     .jpg .jpeg .png .gif .bmp .tiff .webp
```

**共 17 种文件扩展名 + 任意 URL**，覆盖文档/表格/演示/电子书/网页/文本/图片 7 大类。

---

## 7. 我们项目要不要用

### 7.1 现状

`backend/app/workers/parsers.py` 是 80 行的 if-elif 链，4 种格式。能跑，但加 EPUB/PPTX/Web 解析时会变臃肿。

### 7.2 推荐采用范围

| 借鉴 | 不借鉴 |
|---|---|
| BaseParser 抽象 + Document 契约 | gRPC sidecar（Python→Python 不需要） |
| ParserRegistry（单引擎即可，先不做多引擎） | 多引擎派发（MVP 用不到 markitdown vs builtin 的选择） |
| PipelineParser（MarkdownParser 复用价值大） | FirstParser（暂时用不上） |
| 模板方法（parse / parse_into_text 双层） | 600 行 splitter |
| register 一次性注册的初始化风格 | TLS / mTLS / Token Interceptor |

### 7.3 落地结构（草案）

```
backend/app/workers/parsers/
├── __init__.py            # 导出 registry 单例
├── base.py                # BaseParser + Document
├── registry.py            # ParserRegistry（单引擎版本）
├── composite.py           # PipelineParser（可选）
├── pdf_parser.py
├── docx_parser.py
├── markdown_parser.py
├── excel_parser.py        # 后续加
├── epub_parser.py         # 后续加
└── web_parser.py          # 后续加
```

迁移完成后，`parse_document.py` 的核心改动：

```python
# 改造前
from app.workers.parsers import parse_by_filename
text = parse_by_filename(doc.original_filename, raw_bytes)

# 改造后
from app.workers.parsers import registry
parser_cls = registry.get_parser_class("", file_type)
document = parser_cls(file_name=name, file_type=ftype).parse(raw_bytes)
text = document.content
images = document.images  # 未来多模态用
```

---

## 8. 进一步阅读

- 真实代码：`docreader/parser/registry.py`、`base_parser.py`、`chain_parser.py`
- 经典设计模式参考：
  - Strategy: 《Head First 设计模式》第 1 章
  - Registry: Martin Fowler, "Registry" pattern (PoEAA 附录)
  - Composite: 《设计模式》Gamma et al. 第 4 章
  - Template Method: 《设计模式》Gamma et al. 第 5 章
