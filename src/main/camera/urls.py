from django.urls import path
from . import views

urlpatterns = [
    path('set_queue', views.set_queue),
]