from django.urls import path
from . import views


urlpatterns = [
    path('get_notifications', views.get_notifications),
    path('set_notifications_read', views.set_notifications_read),
]
