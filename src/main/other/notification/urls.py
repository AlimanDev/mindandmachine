from django.urls import path
from . import views


urlpatterns = [
    path('get_notifications', views.get_notifications),
    path('get_notifications2', views.get_notifications2),
    path('set_notifications_read', views.set_notifications_read),
    path('do_notify_action', views.do_notify_action),
]
