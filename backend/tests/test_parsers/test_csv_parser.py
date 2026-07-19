"""CSV 解析器契约测试。"""

from importlib import import_module

import pytest

from app.parsers.base import BaseParser
from app.parsers.document import Document


def _csv_parser_class():
    try:
        module = import_module("app.parsers.csv_parser")
    except ModuleNotFoundError:
        pytest.fail("planned module is missing: app.parsers.csv_parser")
    return module.CsvParser


def test_csv_parser_uses_base_parser_contract():
    assert issubclass(_csv_parser_class(), BaseParser)


def test_parses_utf8_semicolon_csv_as_markdown():
    content = "姓名;年龄;备注\n张三;30;A|B\n".encode()
    document = _csv_parser_class()(file_name="people.csv").parse(content)
    assert isinstance(document, Document)
    assert "| 姓名 | 年龄 | 备注 |" in document.content
    assert "| 张三 | 30 | A\\|B |" in document.content
    assert document.metadata == {
        "format": "csv",
        "delimiter": ";",
        "row_count": 2,
        "column_count": 3,
    }


def test_parses_gbk_comma_csv():
    content = "城市,数量\n北京,2\n".encode("gbk")
    document = _csv_parser_class()(file_name="cities.csv").parse(content)
    assert "| 城市 | 数量 |" in document.content
    assert "| 北京 | 2 |" in document.content
    assert document.metadata["delimiter"] == ","


def test_empty_csv_returns_empty_document():
    document = _csv_parser_class()(file_name="empty.csv").parse(b"")
    assert document.content == ""
    assert document.metadata == {
        "format": "csv",
        "delimiter": ",",
        "row_count": 0,
        "column_count": 0,
    }


def test_registry_routes_csv_to_csv_parser():
    parser_class = _csv_parser_class()
    from app.parsers import registry
    assert registry.get_parser_class("csv") is parser_class


def test_csv_dimension_guard_rejects_excessive_rows_and_columns():
    module = import_module("app.parsers.csv_parser")
    validator = getattr(module, "_validate_csv_dimensions", None)
    assert validator is not None, "CSV parser must expose an internal dimension guard"
    with pytest.raises(ValueError, match="csv_too_large"):
        validator(row_count=100_001, column_count=2)
    with pytest.raises(ValueError, match="csv_too_large"):
        validator(row_count=2, column_count=1_001)
