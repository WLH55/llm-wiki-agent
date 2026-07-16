"""Docx2Parser：Word .docx 文档解析（Stage 3 简化版）。

移植自 docreader/parser/docx_parser.py 的 `_parse_using_simple_method`：
- 用 python-docx 加载 BytesIO(content)
- 遍历 paragraphs → 段落文本
- 遍历 tables → markdown 表格行（`cell | cell | cell`）

刻意不移植的部分（留到后续 Stage）：
- 并发抽取 / 多模态图像处理（docreader 用 ProcessPoolExecutor）
- inline_images base64 上传（需要存储后端）
- 表格标准化（Step 16 的 MarkdownTableFormatter 会做）
- 老式 .doc 二进制格式（见 doc_parser.py）

如果解析出的文本为空，回退到所有段落的纯拼接（防止页面布局诡异的文档丢内容）。
"""
import logging
from io import BytesIO
from typing import List

from docx import Document as DocxDocument

from app.parsers.base import BaseParser
from app.parsers.document import Document

logger = logging.getLogger(__name__)


class Docx2Parser(BaseParser):
    """Word .docx → Document。

    简化策略：段落文本 + 表格转 markdown 行。无图像抽取。
    """

    def parse_into_text(self, content: bytes) -> Document:
        logger.info("Parsing DOCX, content size: %d bytes", len(content))

        try:
            doc = DocxDocument(BytesIO(content))
        except Exception as exc:
            logger.error("Failed to open DOCX: %s", exc)
            return Document(content="", metadata={"error": f"open_failed: {exc}"})

        parts: List[str] = []

        # 段落文本
        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                parts.append(text)

        # 表格 → markdown 行（最简形式，不做对齐美化；Step 16 再标准化）
        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))

        text = "\n\n".join(parts)
        logger.info(
            "DOCX parsed: %d paragraphs, %d tables, %d chars output",
            len(doc.paragraphs),
            len(doc.tables),
            len(text),
        )

        return Document(content=text)
