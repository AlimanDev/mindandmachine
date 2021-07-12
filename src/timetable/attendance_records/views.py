from src.base.permissions import Permission
from src.base.views_abstract import BaseModelViewSet
from src.timetable.models import AttendanceRecords
from .filters import AttendanceRecordsFilter
from .serializers import AttendanceRecordsSerializer


class AttendanceRecordsViewSet(BaseModelViewSet):
    permission_classes = [Permission]
    serializer_class = AttendanceRecordsSerializer
    filterset_class = AttendanceRecordsFilter
    openapi_tags = ['AttendanceRecords', ]

    def get_queryset(self):
        return AttendanceRecords.objects
