from django.urls import path
from . import project_views as project

app_name = 'finance'

urlpatterns = [
    path('recalculate/', project.full_recalculation, name='recalculate'),
    path('operations/<str:kind>/<int:pk>/edit/', project.operation_edit, name='operation_edit'),
    path('operations/<str:kind>/<int:pk>/<str:action>/', project.operation_action, name='operation_action'),
]
