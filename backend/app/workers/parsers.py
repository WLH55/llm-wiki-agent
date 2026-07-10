"""
文件解析：PDF / Markdown / Word / TXT
"""
import io
import logging

logger = logging.getLogger(__name__)


def parse_by_filename(filename: str, data: bytes) -> str:
    """根据扩展名分派解析器"""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        return parse_pdf(data)
    if name.endswith((".md", ".markdown")):
        return parse_markdown(data)
    if name.endswith(".txt"):
        return parse_text(data)
    if name.endswith(".docx"):
        return parse_docx(data)
    logger.warning(f"未知扩展名，按文本处理: {filename}")
    return parse_text(data)


def parse_pdf(data: bytes) -> str:
    """PDF → 文本（用 pdfplumber）"""
    import pdfplumber

    parts = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n\n".join(parts)


def parse_markdown(data: bytes) -> str:
    """Markdown → UTF-8 文本"""
    return data.decode("utf-8", errors="replace")


def parse_text(data: bytes) -> str:
    """纯文本"""
    return data.decode("utf-8", errors="replace")


def parse_docx(data: bytes) -> str:
    """Word .docx → 文本（优先 unstructured，回退 python-docx）"""
    try:
        from unstructured.partition_docx import partition_docx

        elements = partition_docx(file=io.BytesIO(data))
        return "\n\n".join(str(el) for el in elements)
    except ImportError:
        try:
            from docx import Document as DocxDocument

            doc = DocxDocument(io.BytesIO(data))
            return "\n\n".join(p.text for p in doc.paragraphs)
        except ImportError:
            logger.error("解析 .docx 需要 unstructured 或 python-docx")
            raise
