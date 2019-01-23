from django.urls import path
from . import views
from django.conf.urls import include
from .notification import urls as notification_urls
from .outsource import urls as outsource_urls


urlpatterns = [
    path('get_regions', views.get_regions),
    path('get_slots', views.get_slots),
    path('get_all_slots', views.get_all_slots),
    path('set_slot', views.set_slot),
    path('create_slot', views.create_slot),
    path('delete_slot', views.delete_slot),
    path('notifications/', include(notification_urls)),
    path('outsource/', include(outsource_urls)),
]
