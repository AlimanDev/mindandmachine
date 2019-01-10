from django.urls import path
from . import views


urlpatterns = [
    path('get_parameters', views.get_parameters),
    path('set_parameters', views.set_parameters),
]