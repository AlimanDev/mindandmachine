from django.conf.urls import url, include
from rest_framework import routers

from src.timetable.views import EmploymentWorkTypeViewSet, WorkerConstraintViewSet
from src.timetable.worker_day.views import WorkerDayViewSet
from src.timetable.work_type_name.views import WorkTypeNameViewSet
from src.timetable.work_type.views import WorkTypeViewSet
from src.timetable.shop_month_stat.views import ShopMonthStatViewSet
from src.timetable.auto_settings.views import AutoSettingsViewSet
from src.timetable.exchange_settings.views import ExchangeSettingsViewSet


router = routers.DefaultRouter()
router.register(r'worker_day', WorkerDayViewSet, basename='WorkerDay')
router.register(r'work_type_name', WorkTypeNameViewSet, basename='WorkTypeName')
router.register(r'work_type', WorkTypeViewSet, basename='WorkType')
router.register(r'employment_work_type', EmploymentWorkTypeViewSet, basename='EmploymentWorkType')
router.register(r'worker_constraint', WorkerConstraintViewSet, basename='WorkerConstraint')
router.register(r'shop_month_stat', ShopMonthStatViewSet, basename='ShopMonthStat')
router.register(r'auto_settings', AutoSettingsViewSet, basename='AutoSettings')
router.register(r'exchange_settings', ExchangeSettingsViewSet, basename='ExchangeSettings')


urlpatterns = [
    url(r'^', include(router.urls)),
]
