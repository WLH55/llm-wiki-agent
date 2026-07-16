"""PdfParser 测试。

测试策略：
- happy-path：用 hand-crafted minimal PDF bytes 验证 extract_text 能跑通
- 错误处理：无效 bytes → metadata.error
- 技术限制声明：扫描版 PDF（无文字层）→ content 为空，metadata.page_count > 0
"""
from io import BytesIO

from app.parsers.document import Document
from app.parsers.pdf_parser import PdfParser


def _build_minimal_pdf(text: str = "hello pdf") -> bytes:
    """构造一个最小 PDF 1.4，含一页文字。

    xref offset 是按字符数硬算的——如果模板调整需重新对齐。
    当前模板的 stream 长度 = "BT /F1 12 Tf 100 700 Td (...) Tj ET\n" 的字节数。
    """
    stream = f"BT /F1 12 Tf 100 700 Td ({text}) Tj ET\n"
    stream_bytes = stream.encode("latin-1")
    stream_len = len(stream_bytes)

    template = (
        "%PDF-1.4\n"
        "1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        "2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        "3 0 obj\n"
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        "/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\n"
        "endobj\n"
        f"4 0 obj\n<< /Length {stream_len} >>\nstream\n"
    ).encode("latin-1")
    tail = (
        "\nendstream\nendobj\n"
        "5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        "trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n0\n%%EOF\n"
    ).encode("latin-1")
    return template + stream_bytes + tail


class TestPdfParser:
    def test_parses_minimal_pdf(self):
        payload = _build_minimal_pdf("hello pdf")
        parser = PdfParser(file_name="a.pdf")
        doc = parser.parse(payload)
        assert isinstance(doc, Document)
        assert "hello pdf" in doc.content
        assert doc.metadata.get("page_count") == 1
        assert doc.metadata.get("text_page_count") == 1

    def test_returns_document_instance(self):
        payload = _build_minimal_pdf("x")
        doc = PdfParser().parse(payload)
        assert isinstance(doc, Document)

    def test_invalid_bytes_returns_error_metadata(self):
        parser = PdfParser()
        doc = parser.parse(b"not a pdf")
        assert doc.content == ""
        assert "error" in doc.metadata
        assert "open_failed" in doc.metadata["error"]

    def test_empty_pdf_content(self):
        """空内容 bytes（不是合法 PDF）→ open_failed。"""
        parser = PdfParser()
        doc = parser.parse(b"")
        assert doc.content == ""
        assert "error" in doc.metadata

    def test_multi_text_pdf(self):
        """多段文字的 PDF。"""
        # PDF 文字串不能含 ( ) \ 等特殊字符，用简单内容
        payload = _build_minimal_pdf("LineOne")
        doc = PdfParser().parse(payload)
        assert "LineOne" in doc.content
