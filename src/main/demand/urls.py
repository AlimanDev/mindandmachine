from django.urls import path
from . import views


urlpatterns = [
    path('get_indicators', views.get_indicators),
    path('get_forecast', views.get_forecast),
    path('set_demand', views.set_demand),
    path('create_predbills', views.create_predbills_request),
    path('set_predbills', views.set_pred_bills)
]
