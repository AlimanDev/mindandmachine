from rest_framework import viewsets

from src.base.permissions import FilteredListPermission
from src.timetable.filters import EmploymentWorkTypeFilter
from src.timetable.models import (
    EmploymentWorkType,
)
from src.timetable.serializers import (
    EmploymentWorkTypeSerializer,
)


class EmploymentWorkTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [FilteredListPermission]
    serializer_class = EmploymentWorkTypeSerializer
    filterset_class = EmploymentWorkTypeFilter
    queryset = EmploymentWorkType.objects.all()
