from django.urls import path
from . import views


urlpatterns = [
    path('get_department', views.get_department),
    path('get_super_shop', views.get_super_shop),
    path('get_super_shop_list', views.get_super_shop_list),
    path('get_notifications', views.get_notifications),
    path('get_new_notifications', views.get_new_notifications),
    path('set_notifications_read', views.set_notifications_read),
]
