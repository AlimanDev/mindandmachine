from django.urls import path
from . import views


urlpatterns = [
    path('get_tabel', views.get_tabel),
    path('get_demand_xlsx', views.get_demand_xlsx),
    path('get_urv_xlsx', views.get_urv_xlsx),
    path('get_department_stats_xlsx', views.get_department_stats_xlsx),
]
