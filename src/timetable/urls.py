from django.conf.urls import url, include
from rest_framework import routers
from src.timetable.views import WorkerDayViewSet, WorkerDayApproveViewSet, EmploymentWorkTypeViewSet, WorkerConstraintViewSet
from src.timetable.work_type_name.views import WorkTypeNameViewSet
from src.timetable.work_type.views import WorkTypeViewSet


router = routers.DefaultRouter()
router.register(r'worker_day', WorkerDayViewSet, basename='WorkerDay')
router.register(r'worker_day_approve', WorkerDayApproveViewSet, basename='WorkerDayApprove')
router.register(r'work_type_name', WorkTypeNameViewSet, basename='WorkTypeName')
router.register(r'work_type', WorkTypeViewSet, basename='WorkType')
router.register(r'employment_work_type', EmploymentWorkTypeViewSet, basename='EmploymentWorkType')
router.register(r'worker_constraint', WorkerConstraintViewSet, basename='WorkerConstraint')


urlpatterns = [
    url(r'^', include(router.urls)),
]