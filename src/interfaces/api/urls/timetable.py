from django.conf.urls import include
from django.urls import re_path
from rest_framework_nested import routers

from src.interfaces.api.urls.base import employment_nested_router
from src.interfaces.api.views.auto_settings import AutoSettingsViewSet
from src.interfaces.api.views.exchange_settings import ExchangeSettingsViewSet
from src.interfaces.api.views.shop_month_stat import ShopMonthStatViewSet
from src.interfaces.api.views.vacancy_black_list import VacancyBlackListViewSet
from src.interfaces.api.views.timetable import EmploymentWorkTypeViewSet
from src.interfaces.api.views.work_type import WorkTypeViewSet
from src.interfaces.api.views.work_type_name import WorkTypeNameViewSet
from src.interfaces.api.views.worker_constraint import WorkerConstraintViewSet
from src.interfaces.api.views.worker_day import WorkerDayViewSet
from src.interfaces.api.views.worker_day_permissions import WorkerDayPermissionsAPIView
from src.interfaces.api.views.timesheet import TimesheetViewSet
from src.interfaces.api.views.attendance_records import AttendanceRecordsViewSet
from src.interfaces.api.views.worker_day_type import WorkerDayTypeViewSet

router = routers.DefaultRouter()
router.register(r'worker_day', WorkerDayViewSet, basename='WorkerDay')
router.register(r'work_type_name', WorkTypeNameViewSet, basename='WorkTypeName')
router.register(r'work_type', WorkTypeViewSet, basename='WorkType')
router.register(r'employment_work_type', EmploymentWorkTypeViewSet, basename='EmploymentWorkType')
router.register(r'shop_month_stat', ShopMonthStatViewSet, basename='ShopMonthStat')
router.register(r'auto_settings', AutoSettingsViewSet, basename='AutoSettings')
router.register(r'exchange_settings', ExchangeSettingsViewSet, basename='ExchangeSettings')
router.register(r'vacancy_black_list', VacancyBlackListViewSet, basename='VacancyBlackList')
router.register(r'timesheet', TimesheetViewSet, basename='Timesheet')
router.register(r'attendance_records', AttendanceRecordsViewSet, basename='AttendanceRecords')
router.register(r'worker_day_type', WorkerDayTypeViewSet, basename='WorkerDayType')

employment_nested_router.register(r'worker_constraint', WorkerConstraintViewSet, basename='WorkerConstraint')

urlpatterns = [
    re_path(r'^', include(router.urls)),
    re_path(r'^', include(employment_nested_router.urls)),
    re_path(r'^worker_day_permissions/$', WorkerDayPermissionsAPIView.as_view(), name='worker_day_permissions')
]
