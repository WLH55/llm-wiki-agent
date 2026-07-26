"""旧版 XLS 解析器契约测试。"""

from importlib import import_module
from io import BytesIO

import pytest
import xlwt

from app.parsers.core.base import BaseParser
from app.parsers.core.document import Document


def _xls_parser_class():
    try:
        module = import_module("app.parsers.implementations.xls")
    except ModuleNotFoundError:
        pytest.fail("planned module is missing: app.parsers.implementations.xls")
    return module.XlsParser


def _multi_sheet_xls_bytes() -> bytes:
    workbook = xlwt.Workbook()
    people = workbook.add_sheet("People")
    rows = (("Name", "Age", "Note"), ("Alice", 30, "A|B"), ("Bob", "", "line1\nline2"))
    for row_index, row in enumerate(rows):
        for column_index, value in enumerate(row):
            people.write(row_index, column_index, value)
    flags = workbook.add_sheet("Flags")
    flags.write(0, 0, "Enabled")
    flags.write(0, 1, "Count")
    flags.write(1, 0, True)
    flags.write(1, 1, 0)
    workbook.add_sheet("Empty")
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def test_xls_parser_uses_base_parser_contract():
    assert issubclass(_xls_parser_class(), BaseParser)


def test_parses_multiple_xls_sheets_as_markdown_tables():
    document = _xls_parser_class()(file_name="book.xls").parse(_multi_sheet_xls_bytes())
    assert isinstance(document, Document)
    assert "## People" in document.content
    assert "| Name | Age | Note |" in document.content
    assert "| Alice | 30 | A\\|B |" in document.content
    assert "| Bob |  | line1<br>line2 |" in document.content
    assert "## Flags" in document.content
    assert "| TRUE | 0 |" in document.content
    assert "## Empty" not in document.content
    assert document.metadata == {
        "format": "xls",
        "sheet_count": 3,
        "parsed_sheet_count": 2,
    }


def test_invalid_xls_returns_error_metadata():
    document = _xls_parser_class()(file_name="broken.xls").parse(b"not an xls file")
    assert document.content == ""
    assert document.metadata["error"].startswith("open_failed:")


def test_registry_routes_xls_to_xls_parser():
    parser_class = _xls_parser_class()
    from app.parsers import registry
    assert registry.get_parser_class("builtin", "xls") is parser_class
