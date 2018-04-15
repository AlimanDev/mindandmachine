from django.urls import path
from . import views


urlpatterns = [
    path('get_time_distribution', views.get_time_distribution),
]
