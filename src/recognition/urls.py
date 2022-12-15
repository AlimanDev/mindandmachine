from django.conf.urls import include
from django.urls import re_path
from rest_framework import routers

from src.recognition.views import (
    TickViewSet,
    TickPhotoViewSet,
    TickPointAuthToken,
    HashSigninAuthToken,
    TickPointViewSet,
    ShopIpAddressViewSet
)
from src.recognition.wfm.views import WorkerDayViewSet

router = routers.DefaultRouter()
router.register(r'worker_days', WorkerDayViewSet, basename='TimeAttendanceWorkerDay')
router.register(r'ticks', TickViewSet, basename='Tick')
router.register(r'tick_photos', TickPhotoViewSet, basename='TickPhoto')
router.register(r'tick_points', TickPointViewSet, basename='TickPoint')
router.register(r'shop_ip_address', ShopIpAddressViewSet, basename='ShopIpAddress')


urlpatterns = [
    re_path(r'^', include(router.urls)),
    re_path(r'^token-auth/', TickPointAuthToken.as_view()),
    re_path(r'^auth/', HashSigninAuthToken.as_view(), name='time_attendance_auth')
]
