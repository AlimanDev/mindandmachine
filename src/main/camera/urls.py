from django.urls import path
from . import views

urlpatterns = [
    path('set_queue', views.set_queue),
    path('set_events', views.set_events),
]
