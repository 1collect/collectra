import calendar
import csv
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from django import forms
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from openpyxl import Workbook
from users.views import permission_required
from .audit import log_action
from .balances import calculate_balance, CATEGORY_LABELS
from .models import Debt, CollectionAgency, Creditor
from .operations import balance_on


class ReportForm(forms.Form):
    period = forms.ChoiceField(label='Период', required=False, choices=[('all', 'Весь период'), ('day', 'День'), ('week', 'Неделя'), ('month', 'Месяц'), ('quarter', 'Квартал'), ('year', 'Год'), ('custom', 'Произвольный период'), ('as_of', 'На дату')])
    day = forms.DateField(label='Опорная дата', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    start = forms.DateField(label='С', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    end = forms.DateField(label='По', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    agency = forms.ModelChoiceField(label='КА', queryset=CollectionAgency.objects.all(), required=False, empty_label='Все КА')
    creditor = forms.ModelChoiceField(label='Кредитор', queryset=Creditor.objects.all(), required=False, empty_label='Все кредиторы')
    status = forms.ChoiceField(label='Статус', required=False, choices=[('', 'Все'), *Debt.Status.choices])
    dbz = forms.CharField(label='ДБЗ', required=False)
    iin = forms.CharField(label='ИИН', required=False)
    payments = forms.ChoiceField(label='Платежи за период', required=False, choices=[('', 'Все'), ('yes', 'Есть'), ('no', 'Нет')])
    writeoffs = forms.ChoiceField(label='Списания за период', required=False, choices=[('', 'Все'), ('yes', 'Есть'), ('no', 'Нет')])
    cession_number = forms.CharField(label='Номер цессии', required=False)
    cession_date = forms.DateField(label='Дата цессии', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    registry_date = forms.DateField(label='Дата реестра', required=False, widget=forms.DateInput(attrs={'type': 'date'}))
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values(): field.widget.attrs['class'] = 'form-control'
    def clean(self):
        data = super().clean()
        if data.get('period') == 'custom':
            if not data.get('start') or not data.get('end'): raise forms.ValidationError('Укажите начало и конец периода.')
            if data['start'] > data['end']: raise forms.ValidationError('Начало периода не может быть позже конца.')
        return data


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
    debts = Debt.objects.select_related('debtor', 'collection_agency', 'original_creditor', 'cession').prefetch_related('payments__refunds', 'expenses', 'writeoffs', 'balance_snapshots').order_by('contract_number')
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
        rows.append({'debt': debt, 'balance': b, 'status_label': dict(Debt.Status.choices).get(b['status'], b['status']), 'paid': sum((p.amount for p in payments), Decimal('0')), 'refunded': refunded, 'written': sum((w.amount for w in writeoffs), Decimal('0'))})
    return rows, start, end


HEADERS = ['ДБЗ', 'ИИН', 'ФИО', 'КА', 'Кредитор', 'Статус', 'Поступления за период', 'Возвраты за период', 'Списания за период', 'Остаток на конец', 'Переплата', *CATEGORY_LABELS.values(), 'Дата закрытия']


def values(row):
    debt, b = row['debt'], row['balance']
    return [debt.contract_number, debt.debtor.iin, debt.debtor.full_name, str(debt.collection_agency or ''), str(debt.original_creditor or ''), dict(Debt.Status.choices).get(b['status'], b['status']), row['paid'], row['refunded'], row['written'], b['outstanding_amount'], b['overpayment_amount'], *[b['current'][f] for f in CATEGORY_LABELS], b['closed_at'] or '']


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


@permission_required('imports.view_debt')
def report(request):
    form = ReportForm(request.GET or {'period': 'all'})
    rows, start, end = ([], None, None)
    if form.is_valid(): rows, start, end = report_rows(form.cleaned_data)
    format = request.GET.get('format')
    if format in ('csv', 'xlsx', 'pdf') and form.is_valid():
        from .project_views import check
        check(request, 'imports.export_debt')
        log_action('report_exported', details={'format': format, 'filters': request.GET.dict(), 'count': len(rows)})
        return export_rows([values(row) for row in rows], format, f'Отчёт по задолженности: {start or "начало"} — {end}')
    totals = {key: sum((row[key] for row in rows), Decimal('0')) for key in ('paid', 'refunded', 'written')}
    totals['outstanding'] = sum((r['balance']['outstanding_amount'] for r in rows), Decimal('0'))
    query = request.GET.copy(); query.pop('format', None); query.pop('page', None)
    return render(request, 'imports/report.html', {'form': form, 'page_obj': Paginator(rows, 50).get_page(request.GET.get('page')), 'totals': totals, 'start': start, 'end': end, 'query_string': query.urlencode()})


@permission_required('imports.view_debt')
def analytics(request):
    rows, _, end = report_rows({'period': 'all'})
    totals = {'count': len(rows), 'outstanding': Decimal('0'), 'overpayment': Decimal('0'), 'paid': Decimal('0'), 'written': Decimal('0'), 'review': 0}
    categories = dict.fromkeys(CATEGORY_LABELS, Decimal('0'))
    statuses = {}
    agencies = {}
    for row in rows:
        b = row['balance']
        for key, field in [('outstanding', 'outstanding_amount'), ('overpayment', 'overpayment_amount'), ('paid', 'paid_amount'), ('written', 'written_off_amount')]: totals[key] += b[field]
        totals['review'] += int(b.get('needs_manual_review', False))
        statuses[b['status']] = statuses.get(b['status'], 0) + 1
        agency = str(row['debt'].collection_agency or 'КА не указано')
        agencies[agency] = agencies.get(agency, Decimal('0')) + b['outstanding_amount']
        for key in categories: categories[key] += b['current'][key]
    bars = [{'label': CATEGORY_LABELS[key], 'amount': value, 'percent': float(value / max(max(categories.values()), Decimal('1')) * 100)} for key, value in categories.items()]
    return render(request, 'imports/analytics.html', {'totals': totals, 'bars': bars, 'statuses': [(dict(Debt.Status.choices).get(key, key), count) for key, count in statuses.items()], 'agencies': agencies.items(), 'day': end})
