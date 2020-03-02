from django.conf.urls import url, include
from rest_framework import routers
from src.timetable.views import WorkerDayViewSet
from src.timetable.work_type_name.views import WorkTypeNameViewSet
from src.timetable.work_type.views import WorkTypeViewSet


router = routers.DefaultRouter()
router.register(r'worker_day', WorkerDayViewSet, basename='WorkerDay')
router.register(r'work_type_name', WorkTypeNameViewSet, basename='WorkTypeName')
router.register(r'work_type', WorkTypeViewSet, basename='WorkType')


urlpatterns = [
    url(r'^', include(router.urls)),
]