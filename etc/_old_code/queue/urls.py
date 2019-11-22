from django.urls import path
from . import views


urlpatterns = [
    path('get_indicators', views.get_indicators),
    path('get_time_distribution', views.get_time_distribution),
    path('process_forecast', views.process_forecast),
    path('set_predict_queue', views.set_predict_queue),
]
