from django.urls import path
from . import views

urlpatterns = [
    path('get_types', views.get_types),
    path('get_cashboxes', views.get_cashboxes),
    path('create_cashbox', views.create_cashbox),
    path('delete_cashbox', views.delete_cashbox),
    path('update_cashbox', views.update_cashbox),
    path('create_work_type', views.create_work_type),
    path('delete_work_type', views.delete_work_type),
    path('edit_work_type', views.edit_work_type),
    path('get_cashboxes_open_time', views.get_cashboxes_open_time),
    # path('get_cashboxes_used_resource', views.get_cashboxes_used_resource),
]
