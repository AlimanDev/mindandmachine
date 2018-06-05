from django.urls import path
from . import views

urlpatterns = [
    path('select_cashiers', views.select_cashiers),
    path('get_table', views.get_table),
    path('get_month_stat', views.get_month_stat),
]
