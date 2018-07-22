from django.urls import path
from . import views


urlpatterns = [
    path('get_tabel', views.get_tabel),
]