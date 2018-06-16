from django.urls import path
from . import views

urlpatterns = [
    path('set_queue', views.set_queue),
    path('get_queue_from_cameras', views.get_queue_from_cameras),
]