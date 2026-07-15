"""BaseParser 抽象基类测试。"""
import pytest

from app.parsers.base import BaseParser
from app.parsers.document import Document


def test_base_parser_cannot_be_instantiated():
    """ABC 阻止 BaseParser 直接实例化。"""
    with pytest.raises(TypeError, match="abstract class"):
        BaseParser()


def test_subclass_without_implementation_cannot_be_instantiated():
    """子类不实现 parse_into_text 也不能实例化。"""
    class IncompleteParser(BaseParser):
        pass

    with pytest.raises(TypeError, match="parse_into_text"):
        IncompleteParser()


def test_subclass_with_implementation_can_be_instantiated():
    """完整实现的子类可以实例化。"""
    class StubParser(BaseParser):
        def parse_into_text(self, content: bytes) -> Document:
            return Document(content=content.decode("utf-8", errors="replace"))

    parser = StubParser(file_name="x.txt")
    assert parser.file_type == "txt"


def test_template_method_parse_calls_subclass_implementation():
    """parse() 模板方法调子类的 parse_into_text。"""
    class StubParser(BaseParser):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.called = False

        def parse_into_text(self, content: bytes) -> Document:
            self.called = True
            return Document(content=content.decode("utf-8"))

    parser = StubParser(file_name="x.txt")
    doc = parser.parse(b"hello")
    assert parser.called is True
    assert doc.content == "hello"
    assert doc.is_valid()


def test_file_type_inferred_from_filename():
    """file_type 没显式传时，从 file_name 扩展名推断。"""
    class StubParser(BaseParser):
        def parse_into_text(self, content: bytes) -> Document:
            return Document()

    parser = StubParser(file_name="report.pdf")
    assert parser.file_type == "pdf"


def test_file_type_explicit_overrides_inference():
    """显式传 file_type 时优先用它。"""
    class StubParser(BaseParser):
        def parse_into_text(self, content: bytes) -> Document:
            return Document()

    parser = StubParser(file_name="data.bin", file_type="custom")
    assert parser.file_type == "custom"
