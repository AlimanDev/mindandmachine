from django.urls import path
from .views import (
    get_workers_to_exchange,
    notify_workers_about_vacancy,
    cancel_vacancy,
    show_vacancy,
)

urlpatterns = [
    path('get_workers_to_exchange', get_workers_to_exchange),
    path('notify_workers_about_vacancy', notify_workers_about_vacancy),
    path('cancel_vacancy', cancel_vacancy),
    path('show_vacancy', show_vacancy),
]
