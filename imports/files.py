"""Rebuild import workbooks from the saved rows."""
from pathlib import PurePosixPath
from tempfile import SpooledTemporaryFile
from math import ceil
from unicodedata import combining, east_asian_width

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.utils import get_column_letter


def text_width(value):
    text = '' if value is None else str(value).expandtabs(4)
    return max((sum(0 if combining(char) else 2 if east_asian_width(char) in ('W', 'F') else 1
                    for char in line) for line in text.splitlines()), default=0)


def import_download_name(record):
    name = PurePosixPath(record.file_name.replace('\\', '/')).name
    name = ''.join(char for char in name if char.isprintable()).strip()
    return f'{PurePosixPath(name).stem or "import-" + str(record.pk)}.xlsx'


def build_import_workbook(record):
    rows = record.items.order_by('row_number', 'pk')
    columns = record.metadata.get('columns')
    if not isinstance(columns, list) or not columns or not all(isinstance(column, str) for column in columns):
        columns = list(dict.fromkeys(
            column for data in rows.values_list('data', flat=True).iterator(chunk_size=500)
            for column in data
        )) or record.import_type.expected_columns
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet('Импорт')
    sheet.freeze_panes = 'A2'

    # A streaming worksheet writes column dimensions before its first row.
    widths = [text_width(column) for column in columns]
    for data in rows.values_list('data', flat=True).iterator(chunk_size=500):
        for index, column in enumerate(columns):
            widths[index] = max(widths[index], text_width(data.get(column)))
    for index, width in enumerate(widths, start=1):
        dimension = sheet.column_dimensions[get_column_letter(index)]
        dimension.width = min(255, max(8, ceil(width * 1.15) + 2))

    def append(values):
        cells = []
        for value in values:
            cell = WriteOnlyCell(sheet, value=value)
            if isinstance(value, str):
                # Keep identifiers, leading zeroes and formula-like input literal.
                cell.data_type = 's'
            cells.append(cell)
        sheet.append(cells)

    append(columns)
    next_row = 2
    for item in rows.iterator(chunk_size=500):
        # Retain skipped empty lines so source row numbers still match the preview.
        while next_row < item.row_number:
            sheet.append([])
            next_row += 1
        append(item.data.get(column) for column in columns)
        next_row += 1
    content = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b')
    try:
        workbook.save(content)
        content.seek(0)
    except Exception:
        content.close()
        raise
    finally:
        workbook.close()
    return content
