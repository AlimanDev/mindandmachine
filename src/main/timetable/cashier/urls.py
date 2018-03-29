from django.urls import path
from . import views

urlpatterns = [
    path('get_cashiers_set', views.get_cashiers_set),
    path('get_cashiers_timetable', views.get_cashier_timetable),
    path('get_cashier_info', views.get_cashier_info),
    path('set_worker_day', views.set_worker_day),
]
