"""文档解析模块（参考 docreader/parser/ 移植）。

公共 API：
- `Document`：parser 输出契约
- `BaseParser`：抽象基类
- `FirstParser` / `PipelineParser`：责任链与管道组合
- `registry`：全局 parser 注册表（已注册默认 parser）

默认注册策略：
- `.txt` → TextParser
- `.md` / `.markdown` → MarkdownParser（PipelineParser：表格标准化 + base64 图片抽取）
- `.docx` → Docx2Parser（python-docx 段落 + 表格）
- `.doc` → DocParser（antiword / catdoc 命令行）
- `.pdf` → PdfParser（pdfplumber 逐页 extract_text）
- `.pptx` → PptxParser（幻灯片文本 + 内嵌媒体）
- `.ppt` → 默认不注册（不调用外部转换器）
- `.csv` → CsvParser（标准库 csv）
- `.xlsx` → ExcelParser
- `.xls` → XlsParser（xlrd）
- `.xlsb` / `.ods` / `.et` → 默认不注册
- `.html` / `.htm` → WebParser（本地 HTML 或 URL bytes）
- `.mhtml` / `.mht` → MHTMLParser（网页 MIME 归档）
- `.epub` → EPUBParser（章节、元数据和内嵌图片）
- 常见位图格式 → ImageParser（Pillow 元数据和 EXIF）
- 高级引擎：`markitdown` / `opendataloader` 以双 key 注册，可选安装
- 未知扩展名 → dispatch 返回 unsupported_type，禁止文本兜底
"""

from app.parsers.core.base import BaseParser
from app.parsers.core.chain import FirstParser, PipelineParser
from app.parsers.core.document import Document
from app.parsers.core.registry import (
    BUILTIN_ENGINE,
    ParserEngineRegistry,
    ParserRegistry,
    registry,
)
from app.parsers.errors import ParseDispatchError, ParserAssetError
from app.parsers.implementations.csv import CsvParser
from app.parsers.implementations.doc import DocParser
from app.parsers.implementations.docx import Docx2Parser
from app.parsers.implementations.epub import EPUBParser
from app.parsers.implementations.excel import ExcelParser
from app.parsers.implementations.image import ImageParser
from app.parsers.implementations.markdown import (
    MarkdownImageBase64,
    MarkdownParser,
    MarkdownTableFormatter,
)
from app.parsers.implementations.markitdown import MarkitdownParser, markitdown_available
from app.parsers.implementations.mhtml import MHTMLParser
from app.parsers.implementations.opendataloader import (
    OpenDataLoaderParser,
    opendataloader_available,
)
from app.parsers.implementations.pdf import PdfParser
from app.parsers.implementations.pptx import PptxParser
from app.parsers.implementations.text import TextParser
from app.parsers.implementations.web import WebParser
from app.parsers.implementations.xls import XlsParser
from app.parsers.schemas import ParseErrorCode, ParseLimits, ParseResult

__all__ = [
    "Document",
    "BaseParser",
    "FirstParser",
    "PipelineParser",
    "BUILTIN_ENGINE",
    "ParserEngineRegistry",
    "ParserRegistry",
    "registry",
    "ParseDispatchError",
    "ParserAssetError",
    "ParseErrorCode",
    "ParseLimits",
    "ParseResult",
    "TextParser",
    "MarkdownParser",
    "MarkdownTableFormatter",
    "MarkdownImageBase64",
    "Docx2Parser",
    "DocParser",
    "PdfParser",
    "ExcelParser",
    "XlsParser",
    "CsvParser",
    "PptxParser",
    "WebParser",
    "MHTMLParser",
    "EPUBParser",
    "ImageParser",
    "MarkitdownParser",
    "OpenDataLoaderParser",
]


def _register_defaults() -> None:
    """批量注册内置与高级解析引擎。"""

    registry.register(
        BUILTIN_ENGINE,
        {
            "txt": TextParser,
            "md": MarkdownParser,
            "markdown": MarkdownParser,
            "docx": Docx2Parser,
            "doc": DocParser,
            "pdf": PdfParser,
            "xlsx": ExcelParser,
            "xls": XlsParser,
            "csv": CsvParser,
            "pptx": PptxParser,
            "html": WebParser,
            "htm": WebParser,
            "mhtml": MHTMLParser,
            "mht": MHTMLParser,
            "epub": EPUBParser,
            "png": ImageParser,
            "jpg": ImageParser,
            "jpeg": ImageParser,
            "gif": ImageParser,
            "webp": ImageParser,
            "bmp": ImageParser,
            "tif": ImageParser,
            "tiff": ImageParser,
        },
        description="内置解析引擎",
    )
    registry.register(
        "markitdown",
        {
            file_type: MarkitdownParser
            for file_type in (
                "md",
                "markdown",
                "pdf",
                "docx",
                "doc",
                "pptx",
                "ppt",
                "xlsx",
                "xls",
                "csv",
            )
        },
        description="Microsoft MarkItDown 解析引擎",
        check_available=markitdown_available,
        unavailable_hint="请安装 MarkItDown 及其文档格式依赖",
    )
    registry.register(
        "opendataloader",
        {"pdf": OpenDataLoaderParser},
        description="OpenDataLoader PDF 解析引擎",
        check_available=opendataloader_available,
        unavailable_hint="请安装 Java 11+ 与 opendataloader-pdf",
    )


_register_defaults()
