from django.urls import path
from . import views

urlpatterns = [
    path('get_workers', views.get_workers),
    path('get_timetable_xlsx', views.get_timetable_xlsx),
    path('get_cashiers_timetable', views.get_cashiers_timetable),
]
