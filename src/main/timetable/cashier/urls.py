from django.urls import path
from . import views

urlpatterns = [
    path('get_cashiers_list', views.get_cashiers_list),
    path('get_not_working_cashiers_list', views.get_not_working_cashiers_list),
    path('select_cashiers', views.select_cashiers),
    path('get_cashier_timetable', views.get_cashier_timetable),
    path('get_cashier_info', views.get_cashier_info),
    path('set_cashier_info_hard', views.set_cashier_info_hard),
    path('set_cashier_info_lite', views.set_cashier_info_lite),
    path('get_worker_day', views.get_worker_day),
    path('set_worker_day', views.set_worker_day),
    path('create_cashier', views.create_cashier),
    path('dublicate_cashier_table', views.dublicate_cashier_table),
    path('delete_cashier', views.delete_cashier),
    path('password_edit', views.password_edit),
    path('change_cashier_info', views.change_cashier_info),
    path('get_worker_day_logs', views.get_worker_day_logs),
    path('delete_worker_day', views.delete_worker_day),
    path('request_worker_day', views.request_worker_day),
    path('get_change_request', views.get_change_request),
    path('handle_change_request', views.handle_worker_day_request),
]

