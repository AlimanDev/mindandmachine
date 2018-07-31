from django.urls import path
from .views import get_workers_to_exchange

urlpatterns = [
    path('get_workers_to_exchange', get_workers_to_exchange)
]
