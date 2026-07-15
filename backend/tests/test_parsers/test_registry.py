"""ParserRegistry 单元测试。

覆盖：
- 基础 CRUD：register / get_parser_class / list_supported
- 护栏行为：非 BaseParser 子类抛 TypeError；未知 file_type 抛 KeyError
- 副作用：重复注册覆盖并打 warning
- 单例：模块级 registry 实例存在
"""
import logging

import pytest

from app.parsers.base import BaseParser
from app.parsers.document import Document
from app.parsers.registry import ParserRegistry, registry as global_registry
from app.parsers.text_parser import TextParser


class _FakeParser(BaseParser):
    """测试用的占位 parser，不参与默认注册。"""

    def parse_into_text(self, content: bytes) -> Document:
        return Document(content="fake")


# ---------- register + get_parser_class ----------


def test_register_and_get():
    """注册后能按 file_type 取到 parser 类。"""
    reg = ParserRegistry()
    reg.register("txt", TextParser)
    assert reg.get_parser_class("txt") is TextParser


def test_register_fake_parser():
    """任意 BaseParser 子类都能注册。"""
    reg = ParserRegistry()
    reg.register("fake", _FakeParser)
    assert reg.get_parser_class("fake") is _FakeParser


# ---------- list_supported ----------


def test_list_supported_sorted():
    """list_supported 返回字典序的 file_type 列表（稳定断言）。"""
    reg = ParserRegistry()
    reg.register("pdf", _FakeParser)
    reg.register("txt", TextParser)
    reg.register("md", _FakeParser)
    assert reg.list_supported() == ["md", "pdf", "txt"]


def test_list_supported_empty():
    """空 registry 返回空列表（不是 None）。"""
    reg = ParserRegistry()
    assert reg.list_supported() == []


# ---------- 护栏行为 ----------


def test_get_unknown_raises_keyerror():
    """未注册的 file_type 抛 KeyError（不在 registry 内做兜底）。"""
    reg = ParserRegistry()
    with pytest.raises(KeyError):
        reg.get_parser_class("unknown")


def test_get_unknown_error_message_lists_supported():
    """KeyError 消息里带上当前支持的格式，便于排错。"""
    reg = ParserRegistry()
    reg.register("txt", TextParser)
    with pytest.raises(KeyError, match="txt"):
        reg.get_parser_class("pdf")


def test_register_non_basparser_raises_typeerror():
    """非 BaseParser 子类抛 TypeError（封装护栏）。"""
    reg = ParserRegistry()
    with pytest.raises(TypeError):
        reg.register("txt", str)


def test_register_instance_raises_typeerror():
    """传实例（而非类）抛 TypeError。"""
    reg = ParserRegistry()
    with pytest.raises(TypeError):
        reg.register("txt", TextParser())


# ---------- 重复注册 ----------


def test_register_same_class_is_idempotent(caplog):
    """同一 file_type + 同一类重复注册：静默，不打 warning。"""
    reg = ParserRegistry()
    reg.register("txt", TextParser)
    with caplog.at_level(logging.WARNING):
        reg.register("txt", TextParser)
    assert not any("Override" in r.message for r in caplog.records)


def test_register_override_logs_warning(caplog):
    """同一 file_type 注册不同类：覆盖并打 warning（帮助发现配置冲突）。"""
    reg = ParserRegistry()
    reg.register("txt", TextParser)
    with caplog.at_level(logging.WARNING):
        reg.register("txt", _FakeParser)
    assert reg.get_parser_class("txt") is _FakeParser
    assert any("Override" in r.message for r in caplog.records)


# ---------- 模块级单例 ----------


def test_module_singleton_exists():
    """模块级单例 registry 存在且类型正确。"""
    assert isinstance(global_registry, ParserRegistry)


def test_module_singleton_independent_from_local():
    """局部 registry 操作不污染全局单例（验证封装）。"""
    before = set(global_registry.list_supported())
    local = ParserRegistry()
    local.register("txt", TextParser)
    local.register("fake", _FakeParser)
    after = set(global_registry.list_supported())
    assert before == after
