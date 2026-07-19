"""文档解析模块（参考 docreader/parser/ 移植）。

公共 API：
- `Document`：parser 输出契约
- `BaseParser`：抽象基类
- `registry`：全局 parser 注册表（已注册默认 parser）

默认注册策略（Stage 3 Step 7-9 起）：
- `.txt` → TextParser
- `.md` / `.markdown` → MarkdownParser（Stage 3 Step 7 最简版；Step 19 升级为 PipelineParser）
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
- 未知扩展名 → Registry 抛 KeyError，由消费方兜底（见 workers/parse_document.py）
"""
from app.parsers.base import BaseParser
from app.parsers.csv_parser import CsvParser
from app.parsers.doc_parser import DocParser
from app.parsers.document import Document
from app.parsers.docx2_parser import Docx2Parser
from app.parsers.epub_parser import EPUBParser
from app.parsers.excel_parser import ExcelParser
from app.parsers.image_parser import ImageParser
from app.parsers.markdown_parser import MarkdownParser
from app.parsers.mhtml_parser import MHTMLParser
from app.parsers.pdf_parser import PdfParser
from app.parsers.ppt_convert import PptxParser
from app.parsers.registry import registry
from app.parsers.text_parser import TextParser
from app.parsers.web_parser import WebParser
from app.parsers.xls_parser import XlsParser

__all__ = [
    "Document",
    "BaseParser",
    "registry",
    "TextParser",
    "MarkdownParser",
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
]


def _register_defaults() -> None:
    """注册默认 parser 集合。

    Stage 5 Step 12：开放 HTML 与 MHTML 网页格式。
    """
    registry.register("txt", TextParser)
    registry.register("md", MarkdownParser)
    registry.register("markdown", MarkdownParser)
    registry.register("docx", Docx2Parser)
    registry.register("doc", DocParser)
    registry.register("pdf", PdfParser)
    registry.register("xlsx", ExcelParser)
    registry.register("xls", XlsParser)
    registry.register("csv", CsvParser)
    registry.register("pptx", PptxParser)
    registry.register("html", WebParser)
    registry.register("htm", WebParser)
    registry.register("mhtml", MHTMLParser)
    registry.register("mht", MHTMLParser)
    registry.register("epub", EPUBParser)
    for file_type in ("png", "jpg", "jpeg", "gif", "webp", "bmp", "tif", "tiff"):
        registry.register(file_type, ImageParser)


_register_defaults()
