import celery
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.viewsets import ViewSet
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework import status
from django.http import HttpResponse
from django.conf import settings

from src.apps.base.models import Shop
from src.apps.base.permissions import Permission
from src.apps.reports import tasks
from src.interfaces.api.serializers.reports import (
    ReportFilterSerializer,
    ConsolidatedTimesheetReportSerializer,
    TikReportSerializer
)
from src.apps.reports.utils.consolidated_timesheet_report import ConsolidatedTimesheetReportGenerator
from src.apps.reports.utils.pivot_tabel import PlanAndFactPivotTabel
from src.common.http import prepare_response

class ReportsViewSet(ViewSet):
    permission_classes = [Permission]

    def _add_filter(self, data, filters, name, query_name):
        if name in data:
            filters[query_name] = data[name]
        return filters

    @action(detail=False, methods=['get'])
    def pivot_tabel(self, request: Request):
        data = ReportFilterSerializer(data=request.query_params)
        data.is_valid(raise_exception=True)
        data = data.validated_data
        filters = {
            'dt__gte': data['dt_from'],
            'dt__lte': data['dt_to'],
        }
        filters = self._add_filter(data, filters, 'shop_ids', 'shop_id__in')
        filters = self._add_filter(data, filters, 'employee_ids', 'employee_id__in')
        filters = self._add_filter(data, filters, 'user_ids', 'worker_id__in')
        filters = self._add_filter(data, filters, 'is_vacancy', 'is_vacancy')
        filters = self._add_filter(data, filters, 'is_outsource', 'is_outsource')
        filters = self._add_filter(data, filters, 'network_ids', 'worker__network_id__in')
        filters = self._add_filter(data, filters, 'work_type_name', 'work_type_name__in')

        pt = PlanAndFactPivotTabel()
        return pt.get_response(**filters)

    @action(detail=False, methods=['get'])
    def consolidated_timesheet_report(self, request: Request):
        serializer = ConsolidatedTimesheetReportSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        shop_ids = serializer.validated_data.get('shop_id__in').split(',')
        shops = list(Shop.objects.filter(id__in=shop_ids))
        if not shops:
            raise NotFound()
        shops_names = ', '.join(s.name for s in shops)
        truncated_shops_names = shops_names[:31]
        dt_from = serializer.validated_data.get('dt_from')
        dt_to = serializer.validated_data.get('dt_to')
        report_content = ConsolidatedTimesheetReportGenerator(
            shops=shops,
            dt_from=dt_from,
            dt_to=dt_to,
            group_by=serializer.validated_data.get('group_by'),
            shops_names=shops_names,
        ).generate(sheet_name=truncated_shops_names)
        return prepare_response(
            report_content,
            output_name=f'Консолидированный отчет об отработанном времени {truncated_shops_names} {dt_from}-{dt_to}.xlsx',
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

    @action(detail=False, methods=['get'])
    def schedule_deviation(self, request: Request):
        '''
        Schedule deviation report, with email support.

        GET /rest_api/report/schedule_deviation

        :params
            dt_from: QOS_DATE_FORMAT, required=True
            dt_to: QOS_DATE_FORMAT, required=True
            shop_ids: list[int], required=True
            employee_id__in: list[int], required=True
            worker_id__in: list[int], required=True
            is_vacancy: list[int], required=True
            is_outsource: list[int], required=True
            worker__network_id__in: list[int], required=True
            work_type_name__in: list[int], required=True
            emails: list[str], required=False
        :return
            content_type: 'application/xlsx' | None (email)
        '''
        serializer = ReportFilterSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        kwargs = serializer.validated_data

        # Move filter fields to a separate dict
        filter_fields = (
            'employee_id__in', 'worker_id__in', 'is_vacancy',
            'is_outsource', 'worker__network_id__in', 'work_type_name__in'
        )
        kwargs['filters']= {}
        for field in filter_fields:
            if field in kwargs:
                kwargs['filters'][field] = kwargs.pop(field)
        kwargs['user_id'] = request.user.id
        kwargs['network_id'] = request.user.network.id
        return self._generate_report(tasks.schedule_deviation_report, kwargs)

    @action(detail=False, methods=['get'])
    def tick(self, request: Request):
        '''
        Tick report (employee attendance), optionally with photos and email support.

        GET /rest_api/report/tick

        :params
            dt_from: str (in QOS_DATE_FORMAT), required=True
            dt_to: str (in QOS_DATE_FORMAT), required=True
            shop_id__in: list[int], required=True
            employee_id__in: list[int], required=False
            with_biometrics: bool, default=False
            emails: list[str], required=False
            format: str, choices=['docx', 'xlsx', 'json'], required=False
        :return
            content_type: 'application/xlsx' | 'application/docx' | 'application/json' | None (email)
        '''
        serializer = TikReportSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        #biometry and photos option must be manually turned on in network settings
        if not request.user.network.biometry_in_tick_report:
            serializer.validated_data.pop('emails', None)
            serializer.validated_data.pop('with_biometrics', None)

        serializer.validated_data['network_id'] = request.user.network_id
        return self._generate_report(tasks.tick_report, serializer.validated_data)

    def _generate_report(self, task: celery.Task, kwargs: dict) -> HttpResponse:
        """
        Decides whether to generate report in-memory (call task function directly)
        or to launch task in background, sending the report via email.
        """
        if kwargs.get('emails'):
            #celery serializes date as dttm, for some reason
            kwargs['dt_from'] = kwargs['dt_from'].strftime(settings.QOS_DATE_FORMAT) 
            kwargs['dt_to'] = kwargs['dt_to'].strftime(settings.QOS_DATE_FORMAT)
            task.delay(**kwargs)
            return Response(status=status.HTTP_202_ACCEPTED)
        else:
            report = task(**kwargs)

            if report['type'] == 'application/json':
                return HttpResponse(report['file'], content_type=report['type'])

            return HttpResponse(
                report['file'],
                content_type=report['type'],
                headers={
                'Content-Disposition': f'attachment; filename="{report["name"]}"'
                }
            )
