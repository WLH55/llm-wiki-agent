"""表格格式识别与 XLSX 输入归一化。"""

import zipfile
from io import BytesIO

from app.parsers.utils.xlsx_repair import validate_xlsx_archive

_XLS_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def detect_excel_format(content: bytes) -> str | None:
    """根据文件内容识别表格格式，不信任文件扩展名。"""
    if content.startswith(_XLS_MAGIC):
        return "xls"
    if not zipfile.is_zipfile(BytesIO(content)):
        return None
    validate_xlsx_archive(content)
    with zipfile.ZipFile(BytesIO(content), "r") as workbook_zip:
        names = {name.replace("\\", "/") for name in workbook_zip.namelist()}
        if "xl/workbook.xml" in names:
            return "xlsx"
        if "xl/workbook.bin" in names:
            return "xlsb"
        if "mimetype" in names:
            mime = workbook_zip.read("mimetype").decode("ascii", errors="ignore")
            if "opendocument.spreadsheet" in mime:
                return "ods"
    return None


def normalize_excel_bytes(content: bytes, file_type: str | None = None) -> bytes:
    """返回原生 XLSX 字节，拒绝需要外部转换的格式。"""
    detected = detect_excel_format(content)
    if detected == "xlsx":
        return content
    raise ValueError(
        f"Unsupported Excel format: {detected or file_type or 'unknown'}; "
        "external conversion is disabled"
    )
