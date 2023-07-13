from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from src.apps.timetable.service import TimetableService
from src.interfaces.frontend_api.serializers.timetable import TimetableHeaderFilterSerializer, \
    TimetableHeaderDataSerializer


swagger_get_header_response = openapi.Schema(
    type=openapi.TYPE_OBJECT,
    properties={
        'days': openapi.Schema(
            type=openapi.TYPE_ARRAY,
            items=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'date': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        format=openapi.FORMAT_DATE
                    ),
                    'day_name': openapi.Schema(type=openapi.TYPE_STRING)
                })),
        'efficiency_metrics': openapi.Schema(
            type=openapi.TYPE_OBJECT,
            properties={'dates_range_from_start_date': openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'coverage': openapi.Schema(type=openapi.TYPE_STRING),
                    'downtime': openapi.Schema(type=openapi.TYPE_STRING),
                    'work_hours_by_load': openapi.Schema(type=openapi.TYPE_STRING),
                    'hours_without_opened_vacancies': openapi.Schema(type=openapi.TYPE_STRING),
                    'hours_with_opened_vacancies': openapi.Schema(type=openapi.TYPE_STRING),
                    'hours_with_breaks': openapi.Schema(type=openapi.TYPE_STRING),
                    'employees_count_without_opened_vacancies': openapi.Schema(type=openapi.TYPE_STRING),
                    'turnover': openapi.Schema(type=openapi.TYPE_STRING),
                    'productivity': openapi.Schema(type=openapi.TYPE_STRING)}
            )})},
)


class TimetableViewSet(viewsets.ViewSet):
    service = TimetableService()

    @swagger_auto_schema(
        query_serializer=TimetableHeaderFilterSerializer(),
        operation_summary='Отдает информацию по дням',
        responses={200: swagger_get_header_response},
        tags=['NEW_FRONT', 'Header'],
    )
    @action(detail=False, methods=['GET'])
    def header(self, request):
        s = TimetableHeaderFilterSerializer(data=request.query_params)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        shop_id = data.get('shop_id')
        start_date = data.get('start_date')
        end_date = data.get('end_date')

        res = self.service.get_header(shop_id, start_date, end_date)
        return Response(TimetableHeaderDataSerializer(res).data, status=200)
