"""文档解析模块。

公共 API：
- `Document`：parser 输出契约
- `BaseParser`：抽象基类
- `FirstParser` / `PipelineParser`：责任链与管道组合
- `registry`：全局 parser 注册表

生产白名单：
- `.txt` → TextParser
- `.md` / `.markdown` → MarkdownParser
- `.docx` → Docx2Parser
- `.doc` → DocParser（antiword / catdoc）
- `.pdf` → PdfParser
- `.pptx` → PptxParser
- `.csv` → CsvParser
- `.xlsx` → ExcelParser
- `.xls` → XlsParser（xlrd）
- `.html` / `.htm` → WebParser（本地 HTML 或 URL bytes）
- `.mhtml` / `.mht` → MHTMLParser
- `.epub` → EPUBParser
- 常见位图格式 → ImageParser（png/jpg/jpeg/gif/webp/bmp/tif/tiff）
- 高级引擎：`markitdown` / `opendataloader`（可选安装）
"""

from app.parsers.core.base import BaseParser
from app.parsers.core.chain import FirstParser, PipelineParser
from app.parsers.core.document import Document
from app.parsers.core.errors import ParseDispatchError, ParserAssetError
from app.parsers.core.registry import BUILTIN_ENGINE, ParserEngineRegistry, registry
from app.parsers.core.schemas import ParseErrorCode, ParseLimits, ParseResult
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

__all__ = [
    "Document",
    "BaseParser",
    "FirstParser",
    "PipelineParser",
    "BUILTIN_ENGINE",
    "ParserEngineRegistry",
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
    """批量注册内置与高级解析引擎（生产白名单）。"""
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
