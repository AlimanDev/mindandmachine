from django.urls import path
from .views import (
    get_workers_to_exchange, notify_workers_lack
)

urlpatterns = [
    path('get_workers_to_exchange', get_workers_to_exchange),
    path('notify_workers_lack', notify_workers_lack)
]
