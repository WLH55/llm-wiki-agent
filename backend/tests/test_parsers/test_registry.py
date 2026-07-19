"""ParserEngineRegistry 单元测试。"""

from importlib import import_module

import pytest

import app.parsers as parsers_package
from app.parsers.base import BaseParser
from app.parsers.document import Document
from app.parsers.markitdown_parser import MarkitdownParser
from app.parsers.opendataloader_parser import OpenDataLoaderParser
from app.parsers.pdf_parser import PdfParser
from app.parsers.registry import ParserRegistry
from app.parsers.registry import registry as global_registry
from app.parsers.text_parser import TextParser

registry_module = import_module("app.parsers.registry")


class _FakeParser(BaseParser):
    """测试用占位 parser。"""

    def parse_into_text(self, content: bytes) -> Document:
        return Document(content="fake")


def _registry_with_builtin() -> ParserRegistry:
    reg = ParserRegistry()
    reg.register("builtin", {"txt": TextParser, "pdf": PdfParser})
    return reg


# ---------- 双 key 路由与 builtin 兜底 ----------


def test_get_parser_class_hits_requested_engine():
    reg = _registry_with_builtin()
    reg.register("markitdown", {"pdf": _FakeParser})

    assert reg.get_parser_class("markitdown", "pdf") is _FakeParser


@pytest.mark.parametrize("engine", ["unknown", "markitdown"])
def test_get_parser_class_falls_back_to_builtin(engine):
    reg = _registry_with_builtin()
    reg.register("markitdown", {"pdf": _FakeParser})

    assert reg.get_parser_class(engine, "txt") is TextParser


def test_get_parser_class_single_argument_uses_builtin():
    reg = _registry_with_builtin()

    assert reg.get_parser_class("pdf") is PdfParser


def test_get_parser_class_final_unknown_error_has_context():
    reg = _registry_with_builtin()

    with pytest.raises(KeyError) as exc_info:
        reg.get_parser_class("markitdown", "docx")

    message = str(exc_info.value)
    assert "markitdown" in message
    assert "docx" in message
    assert "pdf" in message
    assert "txt" in message


def test_register_and_lookup_normalize_engine_and_file_type():
    reg = ParserRegistry()
    reg.register(" MarkItDown ", {" .PDF ": _FakeParser})

    assert reg.get_parser_class(" MARKITDOWN ", " .PDF ") is _FakeParser
    assert reg.get_engine_names() == ["markitdown"]
    assert reg.list_supported(" MARKITDOWN ") == ["pdf"]


def test_register_rejects_empty_normalized_engine():
    reg = ParserRegistry()

    with pytest.raises(ValueError, match="engine"):
        reg.register("   ", {"pdf": PdfParser})


def test_register_rejects_empty_normalized_file_type():
    reg = ParserRegistry()

    with pytest.raises(ValueError, match="file_type"):
        reg.register("custom", {" ... ": PdfParser})


def test_register_rejects_duplicate_normalized_file_types():
    reg = ParserRegistry()

    with pytest.raises(ValueError, match="pdf"):
        reg.register("custom", {"pdf": PdfParser, " .PDF ": _FakeParser})


# ---------- 注册原子性 ----------


def test_register_validates_whole_mapping_before_replacing_engine():
    reg = _registry_with_builtin()

    with pytest.raises(TypeError):
        reg.register("builtin", {"md": _FakeParser, "bad": str})

    assert reg.list_supported() == ["pdf", "txt"]
    assert reg.get_parser_class("txt") is TextParser


def test_register_replaces_the_engine_mapping_as_a_whole():
    reg = ParserRegistry()
    reg.register("custom", {"txt": TextParser, "pdf": PdfParser})
    reg.register("custom", {"md": _FakeParser})

    assert reg.list_supported("custom") == ["md"]


def test_failed_register_preserves_complete_engine_state():
    def old_probe() -> tuple[bool, str]:
        return False, "旧探针原因"

    reg = ParserRegistry()
    reg.register(
        "custom",
        {"txt": TextParser},
        description="旧描述",
        check_available=old_probe,
        unavailable_hint="旧提示",
    )
    before = reg.list_engines()[0]

    with pytest.raises(ValueError):
        reg.register(
            "custom",
            {"pdf": PdfParser, ".PDF": _FakeParser},
            description="新描述",
            check_available=lambda: (True, ""),
            unavailable_hint="新提示",
        )

    assert reg.get_parser_class("custom", "txt") is TextParser
    assert reg.list_supported("custom") == ["txt"]
    assert reg.list_engines()[0] == before


# ---------- 枚举能力 ----------


def test_list_supported_is_sorted_and_unknown_engine_is_empty():
    reg = ParserRegistry()
    reg.register("builtin", {"txt": TextParser, ".md": _FakeParser, "pdf": PdfParser})

    assert reg.list_supported() == ["md", "pdf", "txt"]
    assert reg.list_supported("unknown") == []


def test_get_engine_names_is_sorted():
    reg = ParserRegistry()
    reg.register("zeta", {"txt": TextParser})
    reg.register("builtin", {"txt": TextParser})
    reg.register("alpha", {"pdf": PdfParser})

    assert reg.get_engine_names() == ["alpha", "builtin", "zeta"]


def test_list_engines_reports_availability_reason_and_sorted_metadata():
    reg = ParserRegistry()
    reg.register(
        "zeta",
        {"txt": TextParser},
        description="Z 引擎",
        check_available=lambda: (False, "缺少依赖"),
        unavailable_hint="请安装 zeta",
    )
    reg.register("builtin", {"txt": TextParser}, description="内置引擎")
    reg.register(
        "alpha",
        {"pdf": PdfParser},
        description="A 引擎",
        check_available=lambda: (True, ""),
    )

    engines = reg.list_engines()

    assert [item["name"] for item in engines] == ["alpha", "builtin", "zeta"]
    assert engines[0] == {
        "name": "alpha",
        "description": "A 引擎",
        "file_types": ["pdf"],
        "available": True,
        "unavailable_reason": "",
    }
    assert engines[1]["available"] is True
    assert engines[1]["unavailable_reason"] == ""
    assert engines[2]["available"] is False
    assert "缺少依赖" in engines[2]["unavailable_reason"]
    assert "请安装 zeta" in engines[2]["unavailable_reason"]


def test_list_engines_converts_probe_exception_to_unavailable():
    def broken_probe() -> tuple[bool, str]:
        raise RuntimeError("探针失败")

    reg = ParserRegistry()
    reg.register(
        "broken",
        {"txt": TextParser},
        check_available=broken_probe,
        unavailable_hint="检查运行环境",
    )

    engine = reg.list_engines()[0]

    assert engine["available"] is False
    assert "探针失败" in engine["unavailable_reason"]
    assert "检查运行环境" in engine["unavailable_reason"]


def test_list_engines_always_reports_builtin_available():
    reg = ParserRegistry()
    reg.register(
        "builtin",
        {"txt": TextParser},
        check_available=lambda: (False, "forced down"),
        unavailable_hint="不应出现",
    )

    engine = reg.list_engines()[0]

    assert engine["available"] is True
    assert engine["unavailable_reason"] == ""


def test_list_engines_never_calls_builtin_probe():
    probe_calls = 0

    def raising_probe() -> tuple[bool, str]:
        nonlocal probe_calls
        probe_calls += 1
        raise RuntimeError("builtin probe 不应执行")

    reg = ParserRegistry()
    reg.register("builtin", {"txt": TextParser}, check_available=raising_probe)

    engine = reg.list_engines()[0]

    assert probe_calls == 0
    assert engine["available"] is True
    assert engine["unavailable_reason"] == ""


@pytest.mark.parametrize(
    "probe_result",
    [(False, None), ("false", "")],
    ids=["non-string-reason", "non-bool-available"],
)
def test_list_engines_converts_malformed_probe_result_to_unavailable(probe_result):
    reg = ParserRegistry()
    reg.register(
        "malformed",
        {"txt": TextParser},
        check_available=lambda: probe_result,
        unavailable_hint="检查探针实现",
    )

    engine = reg.list_engines()[0]

    assert engine["available"] is False
    assert "可用性检查返回值无效" in engine["unavailable_reason"]
    assert "检查探针实现" in engine["unavailable_reason"]


# ---------- 兼容别名与全局默认映射 ----------


def test_compatibility_aliases_and_package_exports():
    engine_registry_cls = getattr(registry_module, "ParserEngineRegistry", None)

    assert getattr(registry_module, "BUILTIN_ENGINE", None) == "builtin"
    assert ParserRegistry is engine_registry_cls
    assert parsers_package.ParserRegistry is engine_registry_cls
    assert parsers_package.ParserEngineRegistry is engine_registry_cls
    assert parsers_package.BUILTIN_ENGINE == "builtin"
    assert isinstance(global_registry, engine_registry_cls)


def test_global_registry_has_three_default_engines():
    assert global_registry.get_engine_names() == [
        "builtin",
        "markitdown",
        "opendataloader",
    ]
    assert global_registry.get_parser_class("pdf") is PdfParser
    assert global_registry.get_parser_class("markitdown", "pdf") is MarkitdownParser
    assert global_registry.get_parser_class("opendataloader", "pdf") is OpenDataLoaderParser
    assert global_registry.list_supported("markitdown") == [
        "csv",
        "doc",
        "docx",
        "markdown",
        "md",
        "pdf",
        "ppt",
        "pptx",
        "xls",
        "xlsx",
    ]
    assert global_registry.list_supported("opendataloader") == ["pdf"]
