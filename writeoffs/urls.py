from django.urls import path
from . import views

app_name = 'writeoffs'

urlpatterns = [
    path('writeoffs/', views.writeoff_list, name='writeoffs'),
    path('writeoffs/<int:record_id>/history/', views.writeoff_history, name='writeoff_history'),
]
