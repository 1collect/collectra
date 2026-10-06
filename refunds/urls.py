from django.urls import path
from . import views

app_name = 'refunds'

urlpatterns = [
    path('refunds/', views.refund_list, name='refunds'),
    path('refunds/new/', views.refund_create, name='refund_new'),
]
