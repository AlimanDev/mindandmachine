from django.urls import path
from . import views

urlpatterns = [
    path('get_types', views.get_types),
    path('get_cashboxes', views.get_cashboxes),
    path('create_cashbox', views.create_cashbox),
    path('delete_cashbox', views.delete_cashbox),
    path('update_cashbox', views.update_cashbox),
    path('create_cashbox_type', views.create_cashbox_type),
    path('delete_cashbox_type', views.delete_cashbox_type)
]
