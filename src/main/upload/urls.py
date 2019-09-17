from django.urls import path
from . import views


urlpatterns = [
    path('upload_demand', views.upload_demand),
    path('upload_timetable', views.upload_timetable),
    path('upload_urv', views.upload_urv),
]
