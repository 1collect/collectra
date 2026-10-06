from django.urls import path
from . import views

app_name = 'references'

urlpatterns = [
    path('collection-agencies/', views.collection_agency_list, name='collection_agencies'),
    path('collection-agencies/new/', views.collection_agency_edit, name='collection_agency_new'),
    path('collection-agencies/<int:agency_id>/edit/', views.collection_agency_edit, name='collection_agency_edit'),
    path('collection-agencies/<int:agency_id>/delete/', views.collection_agency_delete, name='collection_agency_delete'),
    path('counterparties/', views.counterparty_list, name='counterparties'),
    path('counterparties/new/', views.counterparty_edit, name='counterparty_new'),
    path('counterparties/<int:counterparty_id>/edit/', views.counterparty_edit, name='counterparty_edit'),
    path('counterparties/<int:counterparty_id>/delete/', views.counterparty_delete, name='counterparty_delete'),
]
