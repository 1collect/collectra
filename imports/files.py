"""Rebuild import workbooks from the saved rows."""
from pathlib import PurePosixPath
from tempfile import SpooledTemporaryFile
from math import ceil
from unicodedata import combining, east_asian_width
from itertools import chain
from functools import lru_cache

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.utils import get_column_letter
from openpyxl.styles import Alignment

from imports.models import ImportItem


def text_width(value):
    text = '' if value is None else str(value).expandtabs(4)
    return _text_width(text)


@lru_cache(maxsize=8192)
def _text_width(text):
    if text.isascii():
        return max(map(len, text.splitlines()), default=0)
    return max((sum(0 if combining(char) else 2 if east_asian_width(char) in ('W', 'F') else 1
                    for char in line) for line in text.splitlines()), default=0)


def import_download_name(record):
    name = PurePosixPath(record.file_name.replace('\\', '/')).name
    name = ''.join(char for char in name if char.isprintable()).strip()
    return f'{PurePosixPath(name).stem or "import-" + str(record.pk)}.xlsx'


def build_import_workbook(record, *, include_status=False, progress=None, total_rows=None, width_sample=None):
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
    export_columns = [*columns, 'Ошибка'] if include_status else columns
    widths = [text_width(column) for column in export_columns]
    total_rows = rows.count() if total_rows is None else total_rows
    if progress:
        progress(0, 'Чтение данных')

    def row_status(status, error):
        return (error or 'Ошибка') if status == ImportItem.Status.FAILED else 'Нет'

    sizing_rows = rows if width_sample is None else rows[:width_sample]
    for data, status, error in sizing_rows.values_list('data', 'status', 'error_message').iterator(chunk_size=2000):
        for index, column in enumerate(columns):
            widths[index] = max(widths[index], text_width(data.get(column)))
        if include_status:
            widths[-1] = max(widths[-1], text_width(row_status(status, error)))
    for index, width in enumerate(widths, start=1):
        dimension = sheet.column_dimensions[get_column_letter(index)]
        dimension.width = min(255, max(8, ceil(width * 1.15) + 2))

    error_alignment = Alignment(wrap_text=True, vertical='top')

    def append(values):
        cells = []
        for index, value in enumerate(values):
            is_error_column = include_status and index == len(columns) and value is not None
            if is_error_column or (isinstance(value, str) and value.startswith(('=', '#'))):
                cell = WriteOnlyCell(sheet, value=value)
                # Keep identifiers, leading zeroes and formula-like input literal.
                if isinstance(value, str):
                    cell.data_type = 's'
                if is_error_column:
                    cell.alignment = error_alignment
                cells.append(cell)
            else:
                # openpyxl reuses its streaming cell for ordinary values.
                cells.append(value)
        sheet.append(cells)

    append(export_columns)
    if progress:
        progress(10, 'Запись строк')
    next_row = 2
    for index, (row_number, data, status, error) in enumerate(rows.values_list('row_number', 'data', 'status', 'error_message').iterator(chunk_size=2000), start=1):
        # Retain skipped empty lines so source row numbers still match the preview.
        while next_row < row_number:
            sheet.append([])
            next_row += 1
        values = (data.get(column) for column in columns)
        if include_status:
            values = chain(values, [row_status(status, error)])
        append(values)
        next_row += 1
        if progress and (index == 1 or index % 1000 == 0 or index == total_rows):
            progress(min(94, 10 + int(index * 84 / max(total_rows, 1))), 'Запись строк')
    content = SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode='w+b')
    try:
        if progress:
            progress(95, 'Упаковка XLSX')
        workbook.save(content)
        content.seek(0)
    except Exception:
        content.close()
        raise
    finally:
        workbook.close()
    return content
