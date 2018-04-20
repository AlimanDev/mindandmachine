from django.urls import path
from . import views


urlpatterns = [
    path('get_department', views.get_department),
    path('get_super_shop', views.get_super_shop),
    path('get_super_shop_list', views.get_super_shop_list),
]
