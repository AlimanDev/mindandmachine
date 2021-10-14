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
from .utils import get_timesheet_stats
from ..models import Timesheet, TimesheetItem


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
        timesheet_stats = get_timesheet_stats(
            filtered_qs=self.filter_queryset(self.get_queryset()),
            dt_from=Converter.parse_date(self.request.query_params.get('dt__gte')),
            dt_to=Converter.parse_date(self.request.query_params.get('dt__lte')),
            user=self.request.user,
        )
        return Response(timesheet_stats)

    @swagger_auto_schema(
        operation_description='''
        Возвращает данные табеля построчно с группировкой по (сотрудник, тип табеля, подразделение выхода, должность)
        ''',
        responses={},
    )
    @action(detail=False, methods=['get'])
    def lines(self, *args, **kwargs):
        ts_values_list = TimesheetItem.objects.values_list(
            'timesheet_type',
            'shop__code',
            'position__code',
            'employee__tabel_code',
            'dt',
            'day_type',
            'hours_type',
            'hours',
        )
        ts_lines = {}
        for ts_type, shop_code, position_code, employee_table_code, dt, day_type, hours_type, hours in ts_values_list:
            ts_lines.setdefault(
                (ts_type, shop_code, position_code, employee_table_code), {}).setdefault((dt, day_type, hours_type), hours)
        res = []
        for (ts_type, shop_code, position_code, employee__tabel_code), days_dict in ts_lines.items():
            ts_line_data = {}
            ts_line_data['timesheet_type'] = ts_type
            ts_line_data['shop_code'] = shop_code
            ts_line_data['position_code'] = position_code
            ts_line_data['employee__tabel_code'] = employee__tabel_code
            days_list = []
            for (dt, day_type, hours_type), hours in days_dict.items():
                days_list.append(
                    {
                        "dt": dt,
                        "day_type": day_type,
                        "hours_type": hours_type,
                        "hours": hours,
                    }
                )
            ts_line_data['days'] = days_list
            res.append(ts_line_data)
        return Response(res)

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
        calc_timesheets.delay(
            employee_id__in=list(employee_ids),
            dt_from=serializer.data['dt_from'],
            dt_to=serializer.data['dt_to'],
        )
        return Response({'detail': _('Timesheet recalculation started successfully.')})
