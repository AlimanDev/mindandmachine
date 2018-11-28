from django.urls import path
from . import views


urlpatterns = [
    path('get_user_urv', views.get_user_urv),
    path('change_user_urv', views.change_user_urv),
]

