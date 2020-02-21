from django.conf.urls import url, include
from rest_framework import routers
from src.timetable.worker_day.views import WorkerDayViewSet
from src.timetable.work_type_name.views import WorkTypeNameViewSet
from src.timetable.work_type.views import WorkTypeViewSet
from src.timetable.shop_month_stat.views import ShopMonthStatViewSet


router = routers.DefaultRouter()
router.register(r'worker_day', WorkerDayViewSet, basename='WorkerDay')
router.register(r'work_type_name', WorkTypeNameViewSet, basename='WorkTypeName')
router.register(r'work_type', WorkTypeViewSet, basename='WorkType')
router.register(r'shop_month_stat', ShopMonthStatViewSet, basename='ShopMonthStat')

urlpatterns = [
    url(r'^', include(router.urls)),
]