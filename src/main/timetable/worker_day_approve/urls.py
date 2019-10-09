from django.urls import path
from . import views

urlpatterns = [
    path('get_worker_day_approves', views.get_worker_day_approves),
    path('create_worker_day_approve', views.create_worker_day_approve),
    path('delete_worker_day_approve', views.delete_worker_day_approve),
]
