import calendar
import csv
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from .balances import CATEGORY_LABELS
from .models import Debt
from .operations import balance_on


def period_bounds(data):
    day = data.get('day') or timezone.localdate()
    period = data.get('period') or 'all'
    if period == 'all': return None, day
    if period in ('day', 'as_of'): return (day if period == 'day' else None), day
    if period == 'custom': return data['start'], data['end']
    if period == 'week':
        start = day - timedelta(days=day.weekday())
        return start, start + timedelta(days=6)
    month = day.month if period == 'month' else ((day.month - 1) // 3 * 3 + 1 if period == 'quarter' else 1)
    start = date(day.year, month, 1)
    last_month = month if period == 'month' else (month + 2 if period == 'quarter' else 12)
    return start, date(day.year, last_month, calendar.monthrange(day.year, last_month)[1])


def report_rows(data):
    start, end = period_bounds(data)
    debts = Debt.objects.select_related('debtor', 'collection_agency', 'original_creditor', 'cession').prefetch_related('payments__refunds', 'expenses', 'writeoffs').order_by('contract_number')
    for key, field in [('agency', 'collection_agency'), ('creditor', 'original_creditor'), ('dbz', 'contract_number__icontains'), ('iin', 'debtor__iin__icontains'), ('cession_number', 'cession__number__icontains'), ('cession_date', 'cession__date'), ('registry_date', 'registry_date')]:
        if data.get(key): debts = debts.filter(**{field: data[key]})
    rows = []
    for debt in debts:
        if debt.registry_date and debt.registry_date > end: continue
        b = balance_on(debt, end)
        if data.get('status') and (not b['status'].startswith('closed_') if data['status'] == 'closed' else b['status'] != data['status']): continue
        payments = [p for p in debt.payments.all() if p.operation_status != 'cancelled' and p.payment_date <= end and (start is None or p.payment_date >= start)]
        writeoffs = [w for w in debt.writeoffs.all() if w.operation_status != 'cancelled' and w.writeoff_date <= end and (start is None or w.writeoff_date >= start)]
        if any(data.get(key) and bool(items) != (data[key] == 'yes') for key, items in [('payments', payments), ('writeoffs', writeoffs)]): continue
        refunded = sum((r.amount for p in debt.payments.all() for r in p.refunds.all() if p.operation_status != 'cancelled' and r.status == 'active' and r.refund_date <= end and (start is None or r.refund_date >= start)), Decimal('0'))
        rows.append({'debt': debt, 'balance': b, 'paid': sum((p.amount for p in payments), Decimal('0')), 'refunded': refunded, 'written': sum((w.amount for w in writeoffs), Decimal('0'))})
    return rows, start, end


HEADERS = ['ДБЗ', 'ИИН', 'ФИО', 'КА', 'Кредитор', 'Поступления за период', 'Возвраты за период', 'Списания за период', 'Остаток на конец', 'Переплата', *CATEGORY_LABELS.values(), 'Дата закрытия']


def values(row):
    debt, b = row['debt'], row['balance']
    return [debt.contract_number, debt.debtor.iin, debt.debtor.full_name, str(debt.collection_agency or ''), str(debt.original_creditor or ''), row['paid'], row['refunded'], row['written'], b['outstanding_amount'], b['overpayment_amount'], *[b['current'][f] for f in CATEGORY_LABELS], b['closed_at'] or '']


def safe_cell(value):
    if isinstance(value, str) and (value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n'))): return "'" + value
    return value


def export_rows(rows, format, title, headers=HEADERS):
    if format == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response.write('\ufeff')
        writer = csv.writer(response, delimiter=';')
        writer.writerow(headers)
        writer.writerows([[safe_cell(v) for v in row] for row in rows])
    elif format == 'xlsx':
        book = Workbook()
        sheet = book.active
        sheet.title = 'Отчёт'
        sheet.append(headers)
        for row in rows: sheet.append([safe_cell(v) for v in row])
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
        for col in sheet.columns: sheet.column_dimensions[col[0].column_letter].width = min(45, max(18, len(str(col[0].value)) + 2))
        stream = BytesIO()
        book.save(stream)
        response = HttpResponse(stream.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    else:
        from reportlab.pdfgen import canvas
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.lib.pagesizes import A4, landscape
        font_paths = [Path('C:/Windows/Fonts/arial.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')]
        font_path = next((p for p in font_paths if p.exists()), None)
        if not font_path: raise RuntimeError('Для PDF требуется шрифт Arial или DejaVu Sans.')
        if 'ReportUnicode' not in pdfmetrics.getRegisteredFontNames(): pdfmetrics.registerFont(TTFont('ReportUnicode', str(font_path)))
        stream = BytesIO()
        pdf = canvas.Canvas(stream, pagesize=landscape(A4))
        width, height = landscape(A4)
        y = height - 35
        pdf.setTitle(title)
        # One case block per row preserves all columns without tiny type.
        for index, row in enumerate(rows):
            lines = [f'{header}: {value}' for header, value in zip(headers, row)]
            for text in ([title] if index == 0 else []) + lines + ['']:
                while text:
                    if y < 35: pdf.showPage(); y = height - 35
                    pdf.setFont('ReportUnicode', 10)
                    cut = len(text)
                    while pdfmetrics.stringWidth(text[:cut], 'ReportUnicode', 10) > width - 70: cut -= 1
                    pdf.drawString(35, y, text[:cut]); y -= 15; text = text[cut:]
                y -= 3
        if not rows: pdf.setFont('ReportUnicode', 12); pdf.drawString(35, y, title + ' — Нет данных')
        pdf.save()
        response = HttpResponse(stream.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="report.{format}"'
    return response
