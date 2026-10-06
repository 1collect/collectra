from django.urls import path

from . import views

app_name = 'users'

urlpatterns = [
    path('', views.user_list, name='list'),
    path('<int:user_id>/edit/', views.user_edit, name='edit'),
    path('<int:user_id>/toggle-active/', views.user_toggle_active, name='toggle_active'),
    path('roles/', views.role_list, name='roles'),
    path('roles/new/', views.role_edit, name='role_new'),
    path('roles/<int:role_id>/edit/', views.role_edit, name='role_edit'),
    path('groups/', views.group_list, name='groups'),
    path('permissions/', views.permission_list, name='permissions'),
]
