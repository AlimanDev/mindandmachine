from django.conf.urls import url, include
from rest_framework import routers

from src.recognition.views import TickViewSet, TickPhotoViewSet, TickPointAuthToken, HashSigninAuthToken
from src.recognition.wfm.views import WorkerDayViewSet

router = routers.DefaultRouter()
router.register(r'worker_days', WorkerDayViewSet, basename='WorkerDayDetails')
router.register(r'ticks', TickViewSet, basename='Tick')
router.register(r'tick_photos', TickPhotoViewSet, basename='TickPhoto')

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^token-auth/', TickPointAuthToken.as_view()),
    url(r'^auth/', HashSigninAuthToken.as_view())
]
