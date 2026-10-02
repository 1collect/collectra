from django.urls import path

from . import views

app_name = 'imports'

urlpatterns = [
    path('', views.import_list, name='list'),
    path('new/', views.import_upload, name='new'),
    path('<int:import_id>/items/', views.import_items, name='items'),
    path('contracts/', views.debt_list, name='debts'),
    path('refunds/', views.refund_list, name='refunds'),
    path('refunds/new/', views.refund_create, name='refund_new'),
    path('counterparties/', views.counterparty_list, name='counterparties'),
    path('counterparties/new/', views.counterparty_edit, name='counterparty_new'),
    path('counterparties/<int:counterparty_id>/edit/', views.counterparty_edit, name='counterparty_edit'),
    path('counterparties/<int:counterparty_id>/delete/', views.counterparty_delete, name='counterparty_delete'),
    path('types/', views.import_type_list, name='types'),
]
