from django.db.models import F

from src.base.permissions import Permission
from src.base.views_abstract import (
    BaseModelViewSet,
)
from .filters import TimesheetFilter
from .serializers import TimesheetSerializer
from ..models import Timesheet


class TimesheetViewSet(BaseModelViewSet):
    serializer_class = TimesheetSerializer
    filterset_class = TimesheetFilter
    permission_classes = [Permission]
    openapi_tags = ['Timesheet', ]

    def get_queryset(self):
        return Timesheet.objects.filter(
            # dt_fired=  # TODO: annotate dt_fired
            employee__user__network_id=self.request.user.network_id,
        ).annotate(
            employee__tabel_code=F('employee__tabel_code'),
        )
