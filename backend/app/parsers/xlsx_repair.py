"""Repair helpers for common XLSX packaging issues."""

import re
import zipfile
from collections.abc import Callable
from io import BytesIO

SST_PART = "xl/sharedStrings.xml"
_SST_OVERRIDE_RE = re.compile(
    r'<Override[^>]*PartName="[^"]*sharedStrings\.xml"[^>]*/>', re.IGNORECASE
)
_SST_REL_RE = re.compile(
    r'<Relationship[^>]*Type="[^"]*sharedStrings"[^>]*/>', re.IGNORECASE
)


def repair_xlsx_bytes(content: bytes) -> bytes | None:
    """Repair dangling or incorrectly named shared-strings package parts."""
    if not zipfile.is_zipfile(BytesIO(content)):
        return None

    # TODO(security): Validate archive member count, uncompressed sizes,
    # compression ratios, encryption flags, and path traversal before opening.
    # XLSX is a ZIP container, so repair helpers must reject hostile archives
    # before reading XML package metadata.
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
            # TODO(security): Avoid reading whole worksheet XML files during
            # repair. This should use bounded reads or prevalidated member
            # sizes so a malformed workbook cannot force large allocations.
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
    # TODO(security): Rewrite incrementally with per-member and total-size caps.
    # The current dict fully decompresses every ZIP member into memory, which is
    # vulnerable to zip bombs and oversized XLSX packages.
    files = {
        info.filename.replace("\\", "/"): source.read(info.filename)
        for info in source.infolist()
    }
    output = BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as target:
        for name, data in transform(files).items():
            target.writestr(name, data)
    return output.getvalue()
