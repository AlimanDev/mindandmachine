from django.urls import path
from . import views


urlpatterns = [
    path('get_outsource_workers', views.get_outsource_workers),
]
