"""Merged-cell normalization for XLSX workbooks."""

import zipfile
from io import BytesIO

from openpyxl import load_workbook


def fill_merged_cells_xlsx(content: bytes) -> bytes:
    """Unmerge ranges and copy each master value into the covered cells."""
    if not zipfile.is_zipfile(BytesIO(content)):
        return content

    # TODO(security): Validate the XLSX archive and worksheet dimensions before
    # loading. openpyxl may decompress large XML parts and a crafted workbook
    # can define huge merged ranges that make the fill loop expensive.
    workbook = load_workbook(BytesIO(content), data_only=True)
    changed = False
    for sheet in workbook.worksheets:
        for merged_range in list(sheet.merged_cells.ranges):
            master = sheet.cell(merged_range.min_row, merged_range.min_col).value
            sheet.unmerge_cells(str(merged_range))
            for row in range(merged_range.min_row, merged_range.max_row + 1):
                for column in range(merged_range.min_col, merged_range.max_col + 1):
                    sheet.cell(row, column).value = master
            changed = True

    if not changed:
        return content
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
