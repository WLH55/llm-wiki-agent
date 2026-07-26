"""使用 Python 标准库解析 CSV。"""

import csv
from io import StringIO

from app.parsers.core.base import BaseParser
from app.parsers.core.document import Document
from app.parsers.implementations.excel import _sheet_to_markdown
from app.parsers.utils.encoding import decode_bytes

MAX_CSV_ROWS = 100_000
MAX_CSV_COLUMNS = 1_000


class CsvParser(BaseParser):
    """将分隔文本表格解析为 Markdown 表格。"""

    def parse_into_text(self, content: bytes) -> Document:
        text = decode_bytes(content).lstrip("\ufeff")
        delimiter = _detect_delimiter(text)
        rows = []
        for row in csv.reader(StringIO(text), delimiter=delimiter) if text else ():
            _validate_csv_dimensions(len(rows) + 1, len(row))
            rows.append(row)
        column_count = max((len(row) for row in rows), default=0)
        return Document(
            content=_sheet_to_markdown(rows),
            metadata={
                "format": "csv",
                "delimiter": delimiter,
                "row_count": len(rows),
                "column_count": column_count,
            },
        )


def _validate_csv_dimensions(row_count: int, column_count: int) -> None:
    if row_count > MAX_CSV_ROWS or column_count > MAX_CSV_COLUMNS:
        raise ValueError(
            f"csv_too_large: {row_count} rows x {column_count} columns"
        )


def _detect_delimiter(text: str) -> str:
    if not text:
        return ","
    try:
        return csv.Sniffer().sniff(text[:4096], delimiters=",;\t").delimiter
    except csv.Error:
        return ","
