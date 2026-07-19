"""使用 xlrd 解析旧版 XLS 工作簿。"""

import logging
from typing import Any

import xlrd

from app.parsers.base import BaseParser
from app.parsers.document import Document
from app.parsers.excel_parser import _sheet_to_markdown, _validate_sheet_dimensions

logger = logging.getLogger(__name__)


class XlsParser(BaseParser):
    """将旧版 BIFF XLS 工作表解析为 Markdown 表格。"""

    def parse_into_text(self, content: bytes) -> Document:
        try:
            workbook = xlrd.open_workbook(file_contents=content)
        except Exception as exc:
            logger.error("Failed to open XLS workbook: %s", exc)
            return Document(content="", metadata={"error": f"open_failed: {exc}"})
        sections = []
        try:
            for sheet in workbook.sheets():
                _validate_sheet_dimensions(sheet.name, sheet.nrows, sheet.ncols)
                rows = (
                    [_normalize_cell(sheet.cell(row, column), workbook.datemode) for column in range(sheet.ncols)]
                    for row in range(sheet.nrows)
                )
                table = _sheet_to_markdown(rows)
                if table:
                    sections.append(f"## {sheet.name}\n\n{table}")
        finally:
            workbook.release_resources()
        return Document(
            content="\n\n".join(sections),
            metadata={
                "format": "xls",
                "sheet_count": workbook.nsheets,
                "parsed_sheet_count": len(sections),
            },
        )


def _normalize_cell(cell: Any, datemode: int) -> Any:
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    if cell.ctype == xlrd.XL_CELL_NUMBER and float(cell.value).is_integer():
        return int(cell.value)
    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate_as_datetime(cell.value, datemode).isoformat()
    return cell.value
