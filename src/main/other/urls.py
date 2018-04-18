from django.urls import path
from . import views


urlpatterns = [
    path('get_department', views.get_department),
]
