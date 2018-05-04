from django.urls import path
from . import views

urlpatterns = [
    path('get_status', views.get_status),
    path('set_selected_cashiers', views.set_selected_cashiers),
    path('create_timetable', views.create_timetable),
    path('delete_timetable', views.delete_timetable),
    path('set_timetable', views.set_timetable),
]
