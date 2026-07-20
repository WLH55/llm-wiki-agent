"""PdfParser：PDF 文档解析（Stage 3 简化版）。

移植自 docreader/parser/pdf_parser.py 的 pdfplumber 文字版分支。
Stage 3 刻意不移植：
- PDFScannedParser（扫描版 PDF → OCR，依赖 pypdfium2 + 多模态模型）
- 表格识别 + 向量图形分类
- _route 自动路由（文字版 vs 扫描版）

技术限制（用户教学要点）：
1. **扫描版 PDF 抽不出文字**——pdfplumber 只读文本层，扫描页是图像。
   未来需要 OCR（Stage 14 高级引擎 Markitdown/OpenDataLoader 可承接）。
2. **复杂表格会丢结构**——pdfplumber.extract_tables 在多嵌套表格上不稳定。
   本 Stage 不调用表格抽取，所有内容走 extract_text 拼接，表格会被扁平化。
3. **多栏排版**可能按列错位——pdfplumber 按坐标 y 排序，跨栏阅读顺序可能乱。
   生产场景需要 layout 分析（如 MinerU，留 P4）。

策略：
- pdfplumber.open(BytesIO(content))
- 遍历 pages，每页 extract_text()
- 拼接为 markdown（页与页之间用 `\n\n`）
- metadata 记录 page_count 供消费方决策
"""

import logging
from io import BytesIO

import pdfplumber

from app.parsers.base import BaseParser
from app.parsers.document import Document

logger = logging.getLogger(__name__)


class PdfParser(BaseParser):
    """PDF → Document（仅文字层）。

    简化策略：pdfplumber 逐页 extract_text 拼接。
    不识别表格结构、不处理扫描版、不做 layout 分析。
    """

    def parse_into_text(self, content: bytes) -> Document:
        logger.info("Parsing PDF, content size: %d bytes", len(content))

        try:
            pdf = pdfplumber.open(BytesIO(content))
        except Exception as exc:
            logger.error("Failed to open PDF: %s", exc)
            return Document(content="", metadata={"error": f"open_failed: {exc}"})

        parts: list[str] = []
        page_count = 0
        empty_page_count = 0
        try:
            page_count = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                try:
                    text = page.extract_text() or ""
                except Exception as exc:
                    logger.warning("Page %d extract_text failed: %s", i, exc)
                    text = ""
                if text.strip():
                    parts.append(text.strip())
                else:
                    empty_page_count += 1
        finally:
            pdf.close()

        text = "\n\n".join(parts)
        logger.info(
            "PDF parsed: %d pages, %d pages with text, %d chars output",
            page_count,
            len(parts),
            len(text),
        )

        return Document(
            content=text,
            metadata={
                "page_count": page_count,
                "text_page_count": len(parts),
                "empty_page_count": empty_page_count,
                "is_scanned": page_count > 0 and not parts,
            },
        )
