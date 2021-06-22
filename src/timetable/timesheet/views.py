from django.db.models import F, Sum
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.response import Response

from src.base.permissions import Permission
from src.base.views_abstract import (
    BaseModelViewSet,
)
from src.util.models_converter import Converter
from .filters import TimesheetFilter
from .serializers import TimesheetSerializer
from ..models import Timesheet
from ..worker_day.stat import WorkersStatsGetter


class TimesheetViewSet(BaseModelViewSet):
    serializer_class = TimesheetSerializer
    filterset_class = TimesheetFilter
    permission_classes = [Permission]
    openapi_tags = ['Timesheet', ]

    def get_queryset(self):
        qs = Timesheet.objects.filter(
            # dt_fired=  # TODO: annotate dt_fired
            employee__user__network_id=self.request.user.network_id,
        )
        if self.request.query_params.get('by_code'):
            qs = qs.select_related(
                'employee',
                'shop',
            ).annotate(
                employee__tabel_code=F('employee__tabel_code'),
                shop__code=F('shop__code'),
            )
        return qs

    @swagger_auto_schema(
        operation_description='''
            Возвращает статистику по сотрудникам
            ''',
        responses={},
    )
    @action(detail=False, methods=['get'])
    def stats(self, *args, **kwargs):
        filtered_qs = self.filter_queryset(self.get_queryset())

        timesheet_stats_qs = filtered_qs.values(
            'employee_id',
        ).annotate(
            fact_total_hours_sum=Sum('fact_timesheet_total_hours'),
            fact_day_hours_sum=Sum('fact_timesheet_day_hours'),
            fact_night_hours_sum=Sum('fact_timesheet_night_hours'),
            main_total_hours_sum=Sum('main_timesheet_total_hours'),
            main_day_hours_sum=Sum('main_timesheet_day_hours'),
            main_night_hours_sum=Sum('main_timesheet_night_hours'),
            additional_hours_sum=Sum('additional_timesheet_hours'),
        )
        timesheet_stats = {}
        for ts_data in timesheet_stats_qs:
            k = ts_data.pop('employee_id')
            timesheet_stats[k] = ts_data

        worker_stats = WorkersStatsGetter(
            dt_from=Converter.parse_date(self.request.query_params.get('dt__gte')),
            dt_to=Converter.parse_date(self.request.query_params.get('dt__lte')),
            employee_id__in=timesheet_stats.keys(),
            network=self.request.user.network,
        ).run()
        for employee_id, data in timesheet_stats.items():
            data['norm_hours'] = worker_stats.get(
                employee_id, {}).get('plan', {}).get('approved', {}).get('norm_hours', {}).get('selected_period', None)
            data['sawh_hours'] = worker_stats.get(
                employee_id, {}).get('plan', {}).get('approved', {}).get('sawh_hours', {}).get('selected_period', None)
        return Response(timesheet_stats)