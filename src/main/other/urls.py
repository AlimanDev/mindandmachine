from django.urls import path
from . import views
from django.conf.urls import include
from .notification import urls as notification_urls


urlpatterns = [
    path('get_department', views.get_department),
    path('get_super_shop', views.get_super_shop),
    path('get_super_shop_list', views.get_super_shop_list),
    path('get_slots', views.get_slots),
    path('get_all_slots', views.get_all_slots),
    path('set_slot', views.set_slot),
    path('notifications/', include(notification_urls))
]
