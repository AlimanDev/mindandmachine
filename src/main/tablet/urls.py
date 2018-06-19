from django.urls import path
from . import views


urlpatterns = [
    path('get_cashboxes_info', views.get_cashboxes_info),
]