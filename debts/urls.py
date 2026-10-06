from django.urls import path
from . import views

app_name = 'debts'

urlpatterns = [
    path('contracts/', views.debt_list, name='debts'),
    path('contracts/<int:debt_id>/', views.debt_detail, name='debt_detail'),
]
