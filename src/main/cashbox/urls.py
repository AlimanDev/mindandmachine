from django.urls import path
from . import views

urlpatterns = [
    path('get_types', views.get_types),
]
