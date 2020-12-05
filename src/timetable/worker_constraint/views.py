from src.base.views_abstract import BaseModelViewSet
from src.base.permissions import EmploymentFilteredListPermission
from src.timetable.filters import WorkerConstraintFilter
from src.timetable.models import (
    WorkerConstraint,
)
from src.timetable.serializers import (
    WorkerConstraintSerializer,
    WrappedWorkerConstraintSerializer,
)


class WorkerConstraintViewSet(BaseModelViewSet):
    permission_classes = [EmploymentFilteredListPermission]
    serializer_class = WorkerConstraintSerializer
    filterset_class = WorkerConstraintFilter

    def get_serializer_class(self):
        if self.action == 'create':
            return WrappedWorkerConstraintSerializer

        return super(WorkerConstraintViewSet, self).get_serializer_class()

    def get_queryset(self):
        return WorkerConstraint.objects.filter(employment=self.kwargs.get('employment_pk'))

    def filter_queryset(self, queryset):
        if self.action == 'list':
            return super().filter_queryset(queryset)
        return queryset
