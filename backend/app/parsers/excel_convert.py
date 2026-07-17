"""Excel format detection and optional LibreOffice conversion helpers."""

import os
import shutil
import subprocess
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

_XLS_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def detect_excel_format(content: bytes) -> str | None:
    """Detect supported spreadsheet containers without trusting the suffix."""
    if content.startswith(_XLS_MAGIC):
        return "xls"
    if not zipfile.is_zipfile(BytesIO(content)):
        return None

    # TODO(security): Validate ZIP resource limits before inspecting XLSX-like
    # archives. A tiny upload can expand into huge XML parts or contain too many
    # members, so detection should reject zip bombs before reading any member.
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


def find_soffice() -> str | None:
    """Return the local LibreOffice executable, if installed."""
    executable = shutil.which("soffice") or shutil.which("libreoffice")
    if executable:
        return executable

    candidates = (
        "/usr/lib/libreoffice/program/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    )
    return next((path for path in candidates if os.path.exists(path)), None)


def convert_excel_to_xlsx_bytes(
    content: bytes, suffix: str = ".xlsx"
) -> bytes | None:
    """Convert a spreadsheet to XLSX through headless LibreOffice."""
    # TODO(security): Do not enable this for untrusted uploads until LibreOffice
    # runs in an isolated sandbox with CPU, memory, filesystem, and network
    # limits. Office converters parse complex legacy formats and have a larger
    # attack surface than the in-process XLSX-only path.
    soffice = find_soffice()
    if not soffice:
        return None

    normalized_suffix = suffix if suffix.startswith(".") else f".{suffix}"
    with tempfile.TemporaryDirectory() as temp_dir, tempfile.TemporaryDirectory() as profile:
        source = Path(temp_dir) / f"input{normalized_suffix}"
        source.write_bytes(content)
        command = [
            soffice,
            "--headless",
            f"-env:UserInstallation={Path(profile).as_uri()}",
            "--convert-to",
            "xlsx",
            "--outdir",
            temp_dir,
            str(source),
        ]
        try:
            result = subprocess.run(command, capture_output=True, timeout=120, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None

        converted = next(Path(temp_dir).glob("*.xlsx"), None)
        return converted.read_bytes() if converted else None


def normalize_excel_bytes(content: bytes, file_type: str | None = None) -> bytes:
    """Return XLSX bytes, converting legacy or unusual formats when possible."""
    detected = detect_excel_format(content)
    if detected == "xlsx":
        return content

    # TODO(security): Make external conversion explicit opt-in. The safe default
    # upload path should reject xls/xlsb/ods/et instead of starting LibreOffice.
    suffix = file_type or detected or "xlsx"
    converted = convert_excel_to_xlsx_bytes(content, suffix=suffix)
    if converted and detect_excel_format(converted) == "xlsx":
        return converted
    raise ValueError(
        "Unsupported or unreadable Excel format; LibreOffice conversion is unavailable or failed"
    )
