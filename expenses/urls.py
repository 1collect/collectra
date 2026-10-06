from django.urls import path
from . import views

app_name = 'expenses'

urlpatterns = [
    path('expenses/', views.expense_list, name='expenses'),
    path('expenses/new/', views.expense_create, name='expense_new'),
    path('expenses/<int:record_id>/edit/', views.expense_edit, name='expense_edit'),
    path('expenses/<int:record_id>/history/', views.expense_history, name='expense_history'),
]
