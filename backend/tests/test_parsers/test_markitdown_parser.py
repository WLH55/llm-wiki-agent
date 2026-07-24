"""MarkItDown 高级解析器契约测试。"""

from types import SimpleNamespace

import app.parsers.implementations.markitdown as module
from app.parsers import MarkitdownParser, registry
from app.parsers.implementations.pdf import PdfParser


class _FakeMarkitdown:
    """测试用 MarkItDown 替身。"""

    def __init__(self, text: str = "# 标题") -> None:
        self.text = text
        self.calls: list[dict] = []

    def convert(self, stream, **kwargs):
        self.calls.append({"content": stream.read(), "kwargs": kwargs})
        return SimpleNamespace(text_content=self.text)


def test_markitdown_parser_converts_bytes_to_markdown(monkeypatch):
    fake = _FakeMarkitdown("# Hello\n\n正文")
    monkeypatch.setattr(module, "_create_markitdown", lambda: fake)

    document = MarkitdownParser(file_name="sample.docx").parse(b"doc-bytes")

    assert document.content == "# Hello\n\n正文"
    assert document.metadata["parser_engine"] == "markitdown"
    assert fake.calls[0]["content"] == b"doc-bytes"
    assert fake.calls[0]["kwargs"]["file_extension"] == ".docx"
    assert fake.calls[0]["kwargs"]["keep_data_uris"] is True


def test_markitdown_available_reports_missing_dependency(monkeypatch):
    def missing_package():
        raise ImportError("missing markitdown")

    monkeypatch.setattr(module, "_load_markitdown_class", missing_package)

    ok, message = module.markitdown_available()

    assert ok is False
    assert "markitdown 未安装" in message


def test_markitdown_parser_returns_error_when_dependency_missing(monkeypatch):
    def missing_engine():
        raise ImportError("missing markitdown")

    monkeypatch.setattr(module, "_create_markitdown", missing_engine)

    document = MarkitdownParser(file_name="sample.pdf").parse(b"%PDF")

    assert document.content == ""
    assert document.metadata["parser_engine"] == "markitdown"
    assert document.metadata["error"].startswith("dependency_unavailable:")


def test_markitdown_parser_returns_error_for_empty_result(monkeypatch):
    monkeypatch.setattr(module, "_create_markitdown", lambda: _FakeMarkitdown(""))

    document = MarkitdownParser(file_name="empty.pdf").parse(b"%PDF")

    assert document.content == ""
    assert document.metadata["error"] == "empty_result"


def test_markitdown_parser_keeps_default_registry_unchanged():
    assert registry.get_parser_class("pdf") is PdfParser
