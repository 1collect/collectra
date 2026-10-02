from django.urls import path

from . import views

app_name = 'imports'

urlpatterns = [
    path('', views.import_list, name='list'),
    path('new/', views.import_upload, name='new'),
    path('<int:import_id>/preview/', views.import_preview, name='preview'),
    path('<int:import_id>/items/', views.import_items, name='items'),
    path('contracts/', views.debt_list, name='debts'),
    path('payments/', views.payment_list, name='payments'),
    path('payments/new/', views.payment_create, name='payment_new'),
    path('payments/<int:record_id>/edit/', views.payment_edit, name='payment_edit'),
    path('payments/<int:record_id>/history/', views.payment_history, name='payment_history'),
    path('expenses/', views.expense_list, name='expenses'),
    path('expenses/new/', views.expense_create, name='expense_new'),
    path('writeoffs/', views.writeoff_list, name='writeoffs'),
    path('writeoffs/new/', views.writeoff_create, name='writeoff_new'),
    path('writeoffs/<int:record_id>/history/', views.writeoff_history, name='writeoff_history'),
    path('expenses/<int:record_id>/edit/', views.expense_edit, name='expense_edit'),
    path('expenses/<int:record_id>/history/', views.expense_history, name='expense_history'),
    path('refunds/', views.refund_list, name='refunds'),
    path('refunds/new/', views.refund_create, name='refund_new'),
    path('counterparties/', views.counterparty_list, name='counterparties'),
    path('counterparties/new/', views.counterparty_edit, name='counterparty_new'),
    path('counterparties/<int:counterparty_id>/edit/', views.counterparty_edit, name='counterparty_edit'),
    path('counterparties/<int:counterparty_id>/delete/', views.counterparty_delete, name='counterparty_delete'),
]
