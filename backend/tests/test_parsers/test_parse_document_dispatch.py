"""parse dispatch 契约测试（不依赖 DB/worker 运行时）。"""
from app.parsers import registry
from app.parsers.base import BaseParser
from app.parsers.dispatch import parse_to_text
from app.parsers.document import Document
from app.parsers.markdown_parser import MarkdownParser
from app.parsers.text_parser import TextParser


class _EngineProbeParser(BaseParser):
    """用于验证 engine 派发是否命中。"""

    def parse_into_text(self, content: bytes) -> Document:
        return Document(content="engine-hit")


def test_parse_to_text_defaults_to_builtin_markdown():
    """未指定 engine 时，.md 走 builtin MarkdownParser。"""
    text = parse_to_text("demo.md", b"# title")
    assert text == "# title"
    assert registry.get_parser_class("md") is MarkdownParser


def test_parse_to_text_uses_explicit_engine(monkeypatch):
    """显式 engine 应命中对应注册 parser。"""
    monkeypatch_reg = type(registry)()
    monkeypatch_reg.register("builtin", {"md": MarkdownParser})
    monkeypatch_reg.register("probe", {"md": _EngineProbeParser})
    monkeypatch.setattr("app.parsers.dispatch.parser_registry", monkeypatch_reg)
    text = parse_to_text("demo.md", b"# title", engine="probe")
    assert text == "engine-hit"


def test_parse_to_text_unknown_extension_falls_back_to_text():
    """未知扩展名兜底 TextParser。"""
    text = parse_to_text("notes.log", b"hello-log")
    assert text == "hello-log"
    assert TextParser().parse(b"hello-log").content == "hello-log"
