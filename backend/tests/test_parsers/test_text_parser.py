"""TextParser 测试。"""
from app.parsers.core.document import Document
from app.parsers.implementations.text import TextParser


def test_parse_utf8_text():
    """UTF-8 文本能正常解析。"""
    parser = TextParser(file_name="notes.txt")
    doc = parser.parse(b"hello world")
    assert doc.content == "hello world"
    assert doc.is_valid()


def test_parse_chinese_utf8():
    """UTF-8 中文。"""
    parser = TextParser(file_name="zh.txt")
    doc = parser.parse("你好世界".encode("utf-8"))
    assert doc.content == "你好世界"


def test_parse_chinese_gbk():
    """GBK 中文（验证 fallback chain 生效）。"""
    parser = TextParser(file_name="gbk.txt")
    doc = parser.parse(b"\xc4\xe3\xba\xc3")  # GBK 的 "你好"
    assert doc.content == "你好"


def test_parse_empty_bytes():
    """空 bytes 返回空 Document。"""
    parser = TextParser(file_name="empty.txt")
    doc = parser.parse(b"")
    assert doc.content == ""
    assert doc.is_valid() is False


def test_file_type_inferred_from_filename():
    """TextParser 继承 BaseParser 的 file_type 推断。"""
    parser = TextParser(file_name="data.log")
    assert parser.file_type == "log"


def test_parse_returns_document_instance():
    """返回类型是 Document。"""
    parser = TextParser()
    doc = parser.parse(b"test")
    assert isinstance(doc, Document)
