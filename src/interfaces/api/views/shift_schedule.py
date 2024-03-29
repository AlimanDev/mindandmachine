from src.apps.base.models import (
    ShiftSchedule,
    ShiftScheduleInterval,
)
from src.apps.base.permissions import Permission
from src.apps.base.views_abstract import BaseModelViewSet
from src.apps.base.shift_schedule.filters import (
    ShiftScheduleFilter,
    ShiftScheduleIntervalFilter,
)
from src.interfaces.api.serializers.shift_schedule import (
    ShiftScheduleSerializer,
    ShiftScheduleIntervalSerializer,
)


class ShiftScheduleViewSet(BaseModelViewSet):
    permission_classes = [Permission]
    serializer_class = ShiftScheduleSerializer
    filterset_class = ShiftScheduleFilter
    openapi_tags = ['ShiftSchedule', ]

    def get_queryset(self):
        return ShiftSchedule.objects.filter(network_id=self.request.user.network_id)


class ShiftScheduleIntervalViewSet(BaseModelViewSet):
    permission_classes = [Permission]
    serializer_class = ShiftScheduleIntervalSerializer
    filterset_class = ShiftScheduleIntervalFilter
    openapi_tags = ['ShiftScheduleInterval', ]

    def get_queryset(self):
        return ShiftScheduleInterval.objects.filter(
            shift_schedule__network_id=self.request.user.network_id,
            employee__user__network_id=self.request.user.network_id,
        )
