from django.db.models import F, Sum, Q
from django.utils.translation import gettext as _
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from src.base.models import (
    Employment,
    Shop,
)
from src.base.permissions import Permission
from src.base.views_abstract import (
    BaseModelViewSet,
)
from src.util.models_converter import Converter
from .filters import TimesheetFilter
from .serializers import TimesheetSerializer, TimesheetRecalcSerializer
from .tasks import calc_timesheets
from ..models import Timesheet, WorkerDayType
from ..worker_day.stat import WorkersStatsGetter


class TimesheetViewSet(BaseModelViewSet):
    serializer_class = TimesheetSerializer
    filterset_class = TimesheetFilter
    permission_classes = [Permission]
    openapi_tags = ['Timesheet', ]

    def get_queryset(self):
        qs = Timesheet.objects.filter(
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
            fact_total_all_hours_sum=Sum('fact_timesheet_total_hours'),
            fact_total_work_hours_sum=Sum('fact_timesheet_total_hours', filter=Q(fact_timesheet_type__is_work_hours=True)),
            fact_day_work_hours_sum=Sum('fact_timesheet_day_hours', filter=Q(fact_timesheet_type__is_work_hours=True)),
            fact_night_work_hours_sum=Sum('fact_timesheet_night_hours', filter=Q(fact_timesheet_type__is_work_hours=True)),
            main_total_hours_sum=Sum('main_timesheet_total_hours'),
            main_day_hours_sum=Sum('main_timesheet_day_hours'),
            main_night_hours_sum=Sum('main_timesheet_night_hours'),
            additional_hours_sum=Sum('additional_timesheet_hours'),
        )
        hours_by_types = list(WorkerDayType.objects.filter(
            is_active=True,
            show_stat_in_hours=True,
        ).values_list('code', flat=True))
        if hours_by_types:
            hours_by_types_annotates = {}
            for type_id in hours_by_types:
                hours_by_types_annotates[f'hours_by_type_{type_id}'] = Sum(
                    'fact_timesheet_total_hours', filter=Q(fact_timesheet_type_id=type_id))
            timesheet_stats_qs = timesheet_stats_qs.annotate(**hours_by_types_annotates)

        timesheet_stats = {}
        for ts_data in timesheet_stats_qs:
            k = ts_data.pop('employee_id')
            if hours_by_types:
                hours_by_type_dict = {}
                for type_id in hours_by_types:
                    hours_by_type_dict[type_id] = ts_data.pop(f'hours_by_type_{type_id}')
                ts_data['hours_by_type'] = hours_by_type_dict
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

    @swagger_auto_schema(
        request_body=TimesheetRecalcSerializer,
        responses={200: None},
        operation_description='''
        Пересчет табеля
        '''
    )
    @action(detail=False, methods=['post'], serializer_class=TimesheetRecalcSerializer)
    def recalc(self, *args, **kwargs):
        serializer = TimesheetRecalcSerializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        employee_filter = {}
        if serializer.validated_data.get('employee_id__in'):
            employee_filter['employee_id__in'] = serializer.validated_data['employee_id__in']
        employee_ids = Employment.objects.get_active(
            Shop.objects.get(id=serializer.validated_data['shop_id']).network_id,
            dt_from=serializer.validated_data['dt_from'],
            dt_to=serializer.validated_data['dt_to'],
            shop_id=serializer.validated_data['shop_id'],
            **employee_filter,
        ).values_list('employee_id', flat=True)
        employee_ids = list(employee_ids)
        if not employee_ids:
            raise ValidationError({'detail': _('No employees satisfying the conditions.')})
        calc_timesheets.delay(employee_id__in=list(employee_ids))
        return Response({'detail': _('Timesheet recalculation started successfully.')})
