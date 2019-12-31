from django.conf.urls import url, include
from rest_framework import routers
from src.timetable.worker_day.views import WorkerDayViewSet

router = routers.DefaultRouter()
router.register(r'worker_day', WorkerDayViewSet, basename='WorkerDay')

urlpatterns = [
    url(r'^', include(router.urls)),
]