from django.urls import path
from . import views

urlpatterns = [
    path('select_cashiers', views.select_cashiers),
]
