"""常见 XLSX 打包问题修复工具。"""

import re
import zipfile
from collections.abc import Callable
from io import BytesIO

SST_PART = "xl/sharedStrings.xml"
MAX_XLSX_MEMBER_SIZE = 32 * 1024 * 1024
MAX_XLSX_TOTAL_SIZE = 128 * 1024 * 1024
MAX_XLSX_COMPRESSION_RATIO = 100
_SST_OVERRIDE_RE = re.compile(
    r'<Override[^>]*PartName="[^"]*sharedStrings\.xml"[^>]*/>', re.IGNORECASE
)
_SST_REL_RE = re.compile(
    r'<Relationship[^>]*Type="[^"]*sharedStrings"[^>]*/>', re.IGNORECASE
)


def validate_xlsx_archive(content: bytes) -> None:
    """拒绝声明解压规模超过学习版限制的 XLSX 压缩包。"""
    if not zipfile.is_zipfile(BytesIO(content)):
        raise ValueError("invalid_xlsx_archive")
    total_size = 0
    with zipfile.ZipFile(BytesIO(content), "r") as source:
        for info in source.infolist():
            if info.file_size > MAX_XLSX_MEMBER_SIZE:
                raise ValueError(f"xlsx_member_too_large: {info.filename}")
            total_size += info.file_size
            if total_size > MAX_XLSX_TOTAL_SIZE:
                raise ValueError("xlsx_total_size_too_large")
            ratio = info.file_size / max(info.compress_size, 1)
            if ratio > MAX_XLSX_COMPRESSION_RATIO:
                raise ValueError(f"xlsx_compression_ratio_too_large: {info.filename}")


def repair_xlsx_bytes(content: bytes) -> bytes | None:
    """修复悬空或命名错误的共享字符串部件。"""
    if not zipfile.is_zipfile(BytesIO(content)):
        return None
    validate_xlsx_archive(content)
    with zipfile.ZipFile(BytesIO(content), "r") as source:
        names = {name.replace("\\", "/") for name in source.namelist()}
        shared_strings = next(
            (name for name in names if name.lower().endswith("sharedstrings.xml")), None
        )
        if shared_strings:
            if shared_strings == SST_PART:
                return None
            return _rewrite_zip(
                source,
                lambda files: _rename_shared_strings_part(files, shared_strings),
            )
        if not _package_references_shared_strings(source, names):
            return None
        if _worksheets_use_shared_string_cells(source, names):
            return None
        return _rewrite_zip(source, _strip_shared_strings_manifest)


def _package_references_shared_strings(
    source: zipfile.ZipFile, names: set[str]
) -> bool:
    if "[Content_Types].xml" in names:
        content_types = source.read("[Content_Types].xml").decode(
            "utf-8", errors="replace"
        )
        if "sharedstrings.xml" in content_types.lower():
            return True
    relationships = "xl/_rels/workbook.xml.rels"
    if relationships in names:
        rels = source.read(relationships).decode("utf-8", errors="replace")
        if "sharedstrings" in rels.lower():
            return True
    return False


def _worksheets_use_shared_string_cells(
    source: zipfile.ZipFile, names: set[str]
) -> bool:
    for name in names:
        if name.startswith("xl/worksheets/") and name.endswith(".xml"):
            # ZIP 成员大小已在入口校验；学习版这里直接读取工作表 XML。
            sheet = source.read(name).decode("utf-8", errors="replace")
            if re.search(r'\bt="s"', sheet):
                return True
    return False


def _rename_shared_strings_part(
    files: dict[str, bytes], source_path: str
) -> dict[str, bytes]:
    updated = dict(files)
    updated[SST_PART] = updated.pop(source_path)
    return updated


def _strip_shared_strings_manifest(files: dict[str, bytes]) -> dict[str, bytes]:
    updated = dict(files)
    if "[Content_Types].xml" in updated:
        content_types = updated["[Content_Types].xml"].decode("utf-8")
        updated["[Content_Types].xml"] = _SST_OVERRIDE_RE.sub(
            "", content_types
        ).encode("utf-8")
    relationships = "xl/_rels/workbook.xml.rels"
    if relationships in updated:
        rels = updated[relationships].decode("utf-8")
        updated[relationships] = _SST_REL_RE.sub("", rels).encode("utf-8")
    return updated


def _rewrite_zip(
    source: zipfile.ZipFile,
    transform: Callable[[dict[str, bytes]], dict[str, bytes]],
) -> bytes:
    # ZIP 资源上限已在入口校验；学习版在内存中重写全部成员。
    files = {
        info.filename.replace("\\", "/"): source.read(info.filename)
        for info in source.infolist()
    }
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in transform(files).items():
            target.writestr(name, data)
    return output.getvalue()
