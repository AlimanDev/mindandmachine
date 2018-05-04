from django.urls import path
from . import views

urlpatterns = [
    path('get_cashiers_timetable', views.get_cashiers_timetable),
    path('get_workers', views.get_workers),
]
