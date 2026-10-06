from django.urls import path
from . import views
from . import project_views as project

app_name = 'payments'

urlpatterns = [
    path('payments/<int:pk>/distribution/', project.payment_distribution, name='payment_distribution'),
    path('payments/', views.payment_list, name='payments'),
    path('payments/new/', views.payment_create, name='payment_new'),
    path('payments/<int:record_id>/edit/', views.payment_edit, name='payment_edit'),
    path('payments/<int:record_id>/history/', views.payment_history, name='payment_history'),
]
