from django.urls import path
from . import views

urlpatterns = [
    path('get_cashiers_list', views.get_cashiers_list),
    path('get_todays_cashiers_list', views.get_todays_cashiers_list),
    path('get_cashier_timetable', views.get_cashier_timetable),
    path('get_cashier_info', views.get_cashier_info),
    path('set_cashier_info', views.set_cashier_info),
    path('get_worker_day', views.get_worker_day),
    path('set_worker_day', views.set_worker_day),

    path('create_cashier', views.create_cashier),
    path('delete_cashier', views.delete_cashier),
]
