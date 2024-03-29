from django.db.models import F, Sum, Q, Subquery, OuterRef
from django.utils.translation import gettext as _
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from src.apps.base.models import (
    Employment,
    NetworkConnect,
    Shop,
)
from src.apps.base.permissions import Permission
from src.apps.base.views_abstract import (
    BaseModelViewSet,
)
from src.common.models_converter import Converter
from src.apps.timetable.timesheet.filters import TimesheetFilter
from src.interfaces.api.serializers.timesheet import TimesheetItemSerializer, TimesheetSummarySerializer, TimesheetRecalcSerializer
from src.apps.timetable.timesheet.tasks import calc_timesheets
from src.apps.timetable.timesheet.utils import get_timesheet_stats, TimesheetLinesDataGetter
from src.apps.timetable.models import TimesheetItem


class TimesheetViewSet(BaseModelViewSet):
    serializer_class = TimesheetItemSerializer
    filterset_class = TimesheetFilter
    permission_classes = [Permission]
    openapi_tags = ['Timesheet', ]

    def get_serializer_class(self):
        if self.action == 'list':
            return TimesheetSummarySerializer
        return TimesheetItemSerializer

    def get_queryset(self):
        qs = TimesheetItem.objects.filter(
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

    def list(self, request, *args, **kwargs):
        filtered_qs = self.filter_queryset(self.get_queryset())
        wh_q = Q(Q(day_type__is_dayoff=False) | Q(day_type__is_dayoff=True, day_type__is_work_hours=True))
        grouped_qs = filtered_qs.values(
            'employee_id',
            'employee__tabel_code',
            'dt',
        ).annotate(
            fact_timesheet_type=Subquery(
                TimesheetItem.objects.filter(
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
                ).order_by(
                    '-day_type__ordering'
                ).values_list(
                    'day_type_id', flat=True,
                )[:1]
            ),
            fact_timesheet_total_hours=Sum(F('day_hours') + F('night_hours'), filter=Q(wh_q,
                timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT)),
            fact_timesheet_day_hours=Sum('day_hours', filter=Q(wh_q, timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT)),
            fact_timesheet_night_hours=Sum('night_hours', filter=Q(wh_q, timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT)),
            main_timesheet_type=Subquery(
                TimesheetItem.objects.filter(
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
                ).order_by(
                    '-day_type__ordering'
                ).values_list(
                    'day_type_id', flat=True,
                )[:1]
            ),
            main_timesheet_total_hours=Sum(F('day_hours') + F('night_hours'), filter=Q(
                wh_q, timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)),
            main_timesheet_day_hours=Sum('day_hours', filter=Q(wh_q, timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)),
            main_timesheet_night_hours=Sum('night_hours', filter=Q(wh_q, timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)),
            additional_timesheet_hours=Sum(F('day_hours') + F('night_hours'), filter=Q(
                wh_q, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL)),
            additional_timesheet_day_hours=Sum(F('day_hours'), filter=Q(
                wh_q, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL)),
            additional_timesheet_night_hours=Sum(F('night_hours'), filter=Q(
                wh_q, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL)),
        )

        page = self.paginate_queryset(grouped_qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(grouped_qs, many=True)
        return Response(serializer.data)

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
        Сырые данные табеля
        ''',
        responses={},
    )
    @action(detail=False, methods=['get'])
    def items(self, *args, **kwargs):
        filtered_qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(filtered_qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(filtered_qs, many=True)
        return Response(serializer.data)

    @swagger_auto_schema(
        operation_description='''
        Возвращает данные табеля построчно с группировкой по (сотрудник, тип табеля, подразделение выхода, должность)
        ''',
        responses={},
    )
    @action(detail=False, methods=['get'])
    def lines(self, *args, **kwargs):
        filtered_qs = self.filter_queryset(self.get_queryset())
        ts_lines_data = TimesheetLinesDataGetter(timesheet_qs=filtered_qs, user=self.request.user).get()
        return Response(ts_lines_data)

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
        try:
            shop = Shop.objects.get(id=serializer.validated_data['shop_id'])
        except Shop.DoesNotExist:
            raise ValidationError({'detail': _('No shop found.')})
        employee_ids = Employment.objects.get_active(
            dt_from=serializer.validated_data['dt_from'],
            dt_to=serializer.validated_data['dt_to'],
            extra_q=Q(shop__network=shop.network) |\
                Q(employee__user__network_id__in=NetworkConnect.objects.filter(
                        client__shop=shop
                    ).values_list('outsourcing_id', flat=True)),
            **employee_filter,
        ).values_list('employee_id', flat=True)
        if not employee_ids:
            raise ValidationError({'detail': _('No employees satisfying the conditions.')})
        calc_timesheets.delay(
            employee_id__in=list(employee_ids),
            dt_from=serializer.data['dt_from'],
            dt_to=serializer.data['dt_to'],
        )
        return Response({'detail': _('Timesheet recalculation started successfully.')})
