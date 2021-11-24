from src.base.permissions import Permission
from src.base.views_abstract import BaseModelViewSet
from .filters import ShiftScheduleFilter
from .serializers import ShiftScheduleSerializer


class ShiftScheduleViewSet(BaseModelViewSet):
    permission_classes = [Permission]
    serializer_class = ShiftScheduleSerializer
    filterset_class = ShiftScheduleFilter
    openapi_tags = ['ShiftSchedule',]
