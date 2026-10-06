from django.http import HttpResponsePermanentRedirect
from django.urls import path, reverse

from . import views
from . import project_views as project

app_name = 'imports'

urlpatterns = [
    path('imports/templates/', views.import_templates, name='templates'),
    path('imports/generator/', views.import_generator, name='generator'),
    path('imports/templates/<str:code>/', project.import_template, name='import_template'),
    path('recalculate/', project.full_recalculation, name='recalculate'),
    path('payments/<int:pk>/distribution/', project.payment_distribution, name='payment_distribution'),
    path('operations/<str:kind>/<int:pk>/edit/', project.operation_edit, name='operation_edit'),
    path('operations/<str:kind>/<int:pk>/<str:action>/', project.operation_action, name='operation_action'),
    path('imports/', views.import_list, name='list'),
    path('imports/new/', views.import_upload, name='new'),
    path('imports/status/', views.import_status, name='status'),
    path('imports/<int:import_id>/preview/', views.import_preview, name='preview'),
    path('imports/<int:import_id>/download/', views.import_download, name='download'),
    path('contracts/', views.debt_list, name='debts'),
    path('contracts/<int:debt_id>/', views.debt_detail, name='debt_detail'),
    path('payments/', views.payment_list, name='payments'),
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
    path('collection-agencies/', views.collection_agency_list, name='collection_agencies'),
    path('collection-agencies/new/', views.collection_agency_edit, name='collection_agency_new'),
    path('collection-agencies/<int:agency_id>/edit/', views.collection_agency_edit, name='collection_agency_edit'),
    path('collection-agencies/<int:agency_id>/delete/', views.collection_agency_delete, name='collection_agency_delete'),
    path('counterparties/', views.counterparty_list, name='counterparties'),
    path('counterparties/new/', views.counterparty_edit, name='counterparty_new'),
    path('counterparties/<int:counterparty_id>/edit/', views.counterparty_edit, name='counterparty_edit'),
    path('counterparties/<int:counterparty_id>/delete/', views.counterparty_delete, name='counterparty_delete'),
]


def legacy_data_redirect(request, route_name, **kwargs):
    target = reverse('imports:' + route_name, kwargs=kwargs)
    query = request.META.get('QUERY_STRING', '')
    if query:
        target += '?' + query
    return HttpResponsePermanentRedirect(target, preserve_request=True)


# Keep existing links and submitted forms working at their former addresses.
urlpatterns += [
    path('imports/' + str(route.pattern), legacy_data_redirect, {'route_name': route.name})
    for route in urlpatterns
    if not str(route.pattern).startswith('imports/')
]
