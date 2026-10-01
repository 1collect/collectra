from django.urls import path

from . import views

app_name = 'imports'

urlpatterns = [
    path('', views.import_list, name='list'),
    path('contracts/', views.debt_list, name='debts'),
    path('types/', views.import_type_list, name='types'),
]
