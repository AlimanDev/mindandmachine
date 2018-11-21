from django.urls import path
from . import views


urlpatterns = [
    path('get_user_urv', views.get_user_urv),
]

