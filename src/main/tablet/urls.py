from django.urls import path
from . import views


urlpatterns = [
    path('get_cashboxes_info', views.get_cashboxes_info),
    path('get_cashiers_info', views.get_cashiers_info),
    path('change_cashier_status', views.change_cashier_status),
]
