from django.conf.urls import url, include
from rest_framework_nested import routers

from src.base.urls import employment_nested_router
from src.timetable.auto_settings.views import AutoSettingsViewSet
from src.timetable.exchange_settings.views import ExchangeSettingsViewSet
from src.timetable.shop_month_stat.views import ShopMonthStatViewSet
from src.timetable.vacancy_black_list.views import VacancyBlackListViewSet
from src.timetable.views import EmploymentWorkTypeViewSet
from src.timetable.work_type.views import WorkTypeViewSet
from src.timetable.work_type_name.views import WorkTypeNameViewSet
from src.timetable.worker_constraint.views import WorkerConstraintViewSet
from src.timetable.worker_day.views import WorkerDayViewSet

router = routers.DefaultRouter()
router.register(r'worker_day', WorkerDayViewSet, basename='WorkerDay')
router.register(r'work_type_name', WorkTypeNameViewSet, basename='WorkTypeName')
router.register(r'work_type', WorkTypeViewSet, basename='WorkType')
router.register(r'employment_work_type', EmploymentWorkTypeViewSet, basename='EmploymentWorkType')
router.register(r'shop_month_stat', ShopMonthStatViewSet, basename='ShopMonthStat')
router.register(r'auto_settings', AutoSettingsViewSet, basename='AutoSettings')
router.register(r'exchange_settings', ExchangeSettingsViewSet, basename='ExchangeSettings')
router.register(r'vacancy_black_list', VacancyBlackListViewSet, basename='VacancyBlackList')

employment_nested_router.register(r'worker_constraint', WorkerConstraintViewSet, basename='WorkerConstraint')

urlpatterns = [
    url(r'^', include(router.urls)),
    url(r'^', include(employment_nested_router.urls)),
]
