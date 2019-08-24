from django.urls import path
from . import views


urlpatterns = [
    path('get_department', views.get_department),
    path('add_department', views.add_department),
    path('edit_department', views.edit_department),
    path('get_department_list', views.get_department_list),
    path('get_department_stats', views.get_department_stats),
    path('get_parameters', views.get_parameters),
    path('set_parameters', views.set_parameters),

    # path('get_super_shop', views.get_super_shop),
    # path('edit_super_shop', views.edit_supershop),
    # path('get_super_shop_list', views.get_super_shop_list),
    # path('add_super_shop', views.add_supershop),
    # path('get_super_shop_stats', views.get_supershop_stats),
]
