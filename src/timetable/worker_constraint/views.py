from rest_framework import viewsets

from src.base.permissions import EmploymentFilteredListPermission
from src.timetable.filters import WorkerConstraintFilter
from src.timetable.models import (
    WorkerConstraint,
)
from src.timetable.serializers import (
    WorkerConstraintSerializer,
)


class WorkerConstraintViewSet(viewsets.ModelViewSet):
    permission_classes = [EmploymentFilteredListPermission]
    serializer_class = WorkerConstraintSerializer
    filterset_class = WorkerConstraintFilter

    def get_queryset(self):
        return WorkerConstraint.objects.filter(employment=self.kwargs.get('employment_pk'))

    def filter_queryset(self, queryset):
        if self.action == 'list':
            return super().filter_queryset(queryset)
        return queryset

    def get_serializer(self, *args, **kwargs):
        """ if an array is passed, set serializer to many """
        if isinstance(kwargs.get('data', {}), list):
            kwargs['many'] = True
        return super(WorkerConstraintViewSet, self).get_serializer(*args, **kwargs)
