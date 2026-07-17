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
- `.xlsx` / `.xls` / `.xlsb` / `.ods` / `.et` → ExcelParser
- 未知扩展名 → Registry 抛 KeyError，由消费方兜底（见 workers/parse_document.py）
"""
from app.parsers.base import BaseParser
from app.parsers.doc_parser import DocParser
from app.parsers.docx2_parser import Docx2Parser
from app.parsers.document import Document
from app.parsers.excel_parser import ExcelParser
from app.parsers.markdown_parser import MarkdownParser
from app.parsers.pdf_parser import PdfParser
from app.parsers.registry import registry
from app.parsers.text_parser import TextParser

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
]


def _register_defaults() -> None:
    """注册默认 parser 集合。

    Stage 3 Step 9：追加 .pdf 路由。
    """
    registry.register("txt", TextParser)
    registry.register("md", MarkdownParser)
    registry.register("markdown", MarkdownParser)
    registry.register("docx", Docx2Parser)
    registry.register("doc", DocParser)
    registry.register("pdf", PdfParser)
    for file_type in ("xlsx", "xls", "xlsb", "ods", "et"):
        registry.register(file_type, ExcelParser)


_register_defaults()
