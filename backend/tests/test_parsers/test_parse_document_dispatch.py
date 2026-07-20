"""parse dispatch 契约测试（不依赖 DB/worker 运行时）。"""

import base64

import pytest

from app.parsers import registry
from app.parsers.base import BaseParser
from app.parsers.dispatch import parse_document, parse_to_text
from app.parsers.document import Document
from app.parsers.markdown_parser import MarkdownParser
from app.parsers.result import ParseDispatchError, ParseErrorCode, ParseLimits


class _EngineProbeParser(BaseParser):
    """用于验证 engine 派发是否命中。"""

    def parse_into_text(self, content: bytes) -> Document:
        return Document(content="engine-hit")


class _ErrorParser(BaseParser):
    def parse_into_text(self, content: bytes) -> Document:
        return Document(metadata={"error": "open_failed: corrupt"})


class _ImageParser(BaseParser):
    def parse_into_text(self, content: bytes) -> Document:
        return Document(
            content="![x](images/x.png)",
            images={"images/x.png": base64.b64encode(b"image").decode("ascii")},
        )


def _limits(**overrides) -> ParseLimits:
    values = {
        "max_file_bytes": 100,
        "max_output_chars": 100,
        "max_total_image_bytes": 100,
    }
    values.update(overrides)
    return ParseLimits(**values)


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


def test_parse_document_returns_complete_result():
    result = parse_document("demo.md", b"# title")
    assert result.content == "# title"
    assert result.images == {}
    assert result.metadata == {}
    assert result.engine == "builtin"
    assert result.error_code is None
    assert result.warnings == []


def test_unknown_extension_is_rejected():
    result = parse_document("notes.log", b"hello-log")
    assert result.error_code is ParseErrorCode.UNSUPPORTED_TYPE
    with pytest.raises(ParseDispatchError) as exc_info:
        parse_to_text("notes.log", b"hello-log")
    assert exc_info.value.error_code is ParseErrorCode.UNSUPPORTED_TYPE


def test_explicit_engine_does_not_fallback_to_builtin(monkeypatch):
    isolated = type(registry)()
    isolated.register("builtin", {"md": MarkdownParser})
    isolated.register("probe", {"txt": _EngineProbeParser})
    monkeypatch.setattr("app.parsers.dispatch.parser_registry", isolated)
    result = parse_document("demo.md", b"# title", engine="probe")
    assert result.error_code is ParseErrorCode.ENGINE_UNAVAILABLE


def test_unavailable_engine_is_reported(monkeypatch):
    isolated = type(registry)()
    isolated.register("builtin", {"md": MarkdownParser})
    isolated.register(
        "probe",
        {"md": _EngineProbeParser},
        check_available=lambda: (False, "missing runtime"),
    )
    monkeypatch.setattr("app.parsers.dispatch.parser_registry", isolated)
    result = parse_document("demo.md", b"# title", engine="probe")
    assert result.error_code is ParseErrorCode.ENGINE_UNAVAILABLE


def test_legacy_parser_error_is_mapped(monkeypatch):
    isolated = type(registry)()
    isolated.register("builtin", {"bad": _ErrorParser})
    monkeypatch.setattr("app.parsers.dispatch.parser_registry", isolated)
    result = parse_document("demo.bad", b"bad")
    assert result.error_code is ParseErrorCode.PARSE_FAILED


def test_file_and_output_limits(monkeypatch):
    assert (
        parse_document("a.md", b"too large", limits=_limits(max_file_bytes=2)).error_code
        is ParseErrorCode.TOO_LARGE
    )
    isolated = type(registry)()
    isolated.register("builtin", {"txt": _EngineProbeParser})
    monkeypatch.setattr("app.parsers.dispatch.parser_registry", isolated)
    result = parse_document("a.txt", b"x", limits=_limits(max_output_chars=2))
    assert result.error_code is ParseErrorCode.TOO_LARGE


def test_image_total_limit(monkeypatch):
    isolated = type(registry)()
    isolated.register("builtin", {"img": _ImageParser})
    monkeypatch.setattr("app.parsers.dispatch.parser_registry", isolated)
    result = parse_document("a.img", b"x", limits=_limits(max_total_image_bytes=2))
    assert result.error_code is ParseErrorCode.TOO_LARGE
