from rest_framework import viewsets

from src.base.permissions import FilteredListPermission, EmploymentFilteredListPermission

from src.timetable.serializers import (
    EmploymentWorkTypeSerializer,
    WorkerConstraintSerializer,
)

from src.timetable.filters import EmploymentWorkTypeFilter, WorkerConstraintFilter
from src.timetable.models import (
    EmploymentWorkType,
    WorkerConstraint,
)


class EmploymentWorkTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [FilteredListPermission]
    serializer_class = EmploymentWorkTypeSerializer
    filterset_class = EmploymentWorkTypeFilter
    queryset = EmploymentWorkType.objects.all()


class WorkerConstraintViewSet(viewsets.ModelViewSet):
    permission_classes = [EmploymentFilteredListPermission]
    serializer_class = WorkerConstraintSerializer
    filterset_class = WorkerConstraintFilter
    queryset = WorkerConstraint.objects.all()

    def filter_queryset(self, queryset):
        if self.action == 'list':
            return super().filter_queryset(queryset)
        return queryset

    def get_serializer(self, *args, **kwargs):
        """ if an array is passed, set serializer to many """
        if isinstance(kwargs.get('data', {}), list):
            kwargs['many'] = True
        return super(WorkerConstraintViewSet, self).get_serializer(*args, **kwargs)

