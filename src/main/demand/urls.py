from django.urls import path
from . import views


urlpatterns = [
    path('get_forecast', views.get_forecast),
]
