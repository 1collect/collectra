"""Bounded writes for new contracts, including their opening expenses."""
from .audit import audit_user, record_snapshot
from .balances import calculate_balance
from finance.models import ActionLog, BalanceSnapshot, FinancialRecordHistory
from debts.models import Debt, Debtor
from expenses.models import Expense
from django.utils import timezone


def audit_created(records, actor):
    histories, actions = [], []
    for record in records:
        snapshot = record_snapshot(record)
        histories.append(FinancialRecordHistory(**{record._meta.model_name: record},
            action='created', old_data={}, new_data=snapshot, actor=actor))
        actions.append(ActionLog(actor=actor, action='created', object_type=record._meta.model_name,
            object_id=str(record.pk), details={'old': {}, 'new': snapshot}))
    FinancialRecordHistory.objects.bulk_create(histories, batch_size=500)
    ActionLog.objects.bulk_create(actions, batch_size=500)


def save_contract_batches(items, records, progress=None):
    from imports.services import ImportValidationError
    actor = audit_user.get()
    seen = set()
    balance_fields = ('paid_amount', 'written_off_amount', 'outstanding_amount',
        'overpayment_amount', 'status', 'closed_at', 'needs_manual_review',
        'recalculation_error_message', 'has_overpayment')
    for start in range(0, len(items), 500):
        batch_items, values = items[start:start + 500], records[start:start + 500]
        numbers = [value[0] for value in values]
        if len(set(numbers)) != len(numbers) or seen.intersection(numbers) or Debt.objects.filter(contract_number__in=numbers).exists():
            raise ImportValidationError('ДБЗ уже существует. Импорт файла невозможен.')
        seen.update(numbers)
        iins = {value[1] for value in values}
        existing = set(Debtor.objects.filter(iin__in=iins).values_list('iin', flat=True))
        new = {}
        for item, (_, iin, name, _) in zip(batch_items, values, strict=True):
            if iin not in existing and iin not in new:
                new[iin] = Debtor(iin=iin, full_name=name, import_item=item)
        # Like get_or_create, a concurrent creator must not produce a second borrower.
        Debtor.objects.bulk_create(list(new.values()), ignore_conflicts=True, batch_size=500)
        borrowers = {borrower.iin: borrower for borrower in Debtor.objects.select_for_update().filter(iin__in=iins).order_by('pk')}
        borrower_fields = {'full_name'}
        for _, iin, name, fields in values:
            borrower = borrowers[iin]
            borrower.full_name = name
            for field, value in fields.get('_borrower', {}).items():
                setattr(borrower, field, value)
                borrower_fields.add(field)
        Debtor.objects.bulk_update(list(borrowers.values()), sorted(borrower_fields), batch_size=500)
        debts, opening_expenses = [], []
        for item, (number, iin, _, original) in zip(batch_items, values, strict=True):
            fields = dict(original)
            fields.pop('_borrower', None)
            expenses = fields.pop('_own_expenses', {})
            debt = Debt(contract_number=number, debtor=borrowers[iin], import_item=item, **fields)
            debts.append(debt)
            opening_expenses.append(expenses)
        Debt.objects.bulk_create(debts, batch_size=500)
        expenses = [Expense(debt=debt, import_item=item,
            expense_date=debt.registry_date or timezone.localdate(), **fields)
            for debt, item, fields in zip(debts, batch_items, opening_expenses, strict=True) if any(fields.values())]
        Expense.objects.bulk_create(expenses, batch_size=500)
        debt_ids = [debt.pk for debt in debts]
        # Use database-rounded money, exactly as the ordinary save/recalculate path does.
        debts = list(Debt.objects.filter(pk__in=debt_ids).order_by('pk'))
        expenses = list(Expense.objects.filter(debt_id__in=debt_ids).order_by('pk'))
        audit_created(expenses, actor)
        by_debt = {}
        for expense in expenses:
            by_debt.setdefault(expense.debt_id, []).append(expense)
        snapshots, actions = [], []
        for debt in debts:
            debt._prefetched_objects_cache = {'payments': [], 'writeoffs': [], 'expenses': by_debt.get(debt.pk, [])}
            balance = calculate_balance(debt)
            for field in balance_fields:
                setattr(debt, field, balance[field])
            dates = {operation['date'] for operation in balance['operations']}
            if debt.registry_date:
                dates.add(debt.registry_date)
            dates.add(timezone.localdate())
            for day in sorted(dates):
                snapshot = calculate_balance(debt, as_of=day)
                if not snapshot['needs_manual_review']:
                    snapshots.append(BalanceSnapshot(debt=debt, snapshot_date=day,
                        balances={field: str(value) for field, value in snapshot['current'].items()},
                        **{field: snapshot[field] for field in ('outstanding_amount', 'overpayment_amount',
                            'status', 'closed_at', 'paid_amount', 'written_off_amount')}))
            actions.append(ActionLog(actor=actor,
                action='recalculation_error' if balance['needs_manual_review'] else 'recalculated',
                object_type='debt', object_id=str(debt.pk),
                details={'source': 'recalculation', 'error': balance['recalculation_error_message']}))
        Debt.objects.bulk_update(debts, balance_fields, batch_size=500)
        BalanceSnapshot.objects.bulk_create(snapshots, batch_size=500)
        ActionLog.objects.bulk_create(actions, batch_size=500)
        if progress:
            progress(min(start + 500, len(items)), len(items))
