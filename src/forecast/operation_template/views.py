from datetime import datetime, timedelta
from rest_framework import serializers, viewsets, status
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from django_filters import DateFilter, NumberFilter
from src.base.permissions import FilteredListPermission
from src.forecast.models import OperationTemplate
from src.conf.djconfig import QOS_DATE_FORMAT, QOS_TIME_FORMAT
from src.forecast.operation_template.utils import build_period_clients


# Serializers define the API representation.
class OperationTemplateSerializer(serializers.ModelSerializer):
    tm_start = serializers.TimeField(format=QOS_TIME_FORMAT)
    tm_end = serializers.TimeField(format=QOS_TIME_FORMAT)
    days_in_period = serializers.ListField(allow_empty=True, child=serializers.IntegerField())
    dt_built_to = serializers.DateField(format=QOS_DATE_FORMAT, required=False)
    date_rebuild_from = serializers.DateField(format=QOS_DATE_FORMAT, required=False, write_only=True)
    operation_type_id = serializers.IntegerField(required=False)
    class Meta:
        model = OperationTemplate
        fields = ['id', 'operation_type_id', 'tm_start', 'tm_end', 'period', 'days_in_period', 'dt_built_to', 'value', 'name', 'code', 'date_rebuild_from']

    def is_valid(self, *args, **kwargs):
        super(OperationTemplateSerializer, self).is_valid(*args, **kwargs)
        ot = OperationTemplate(
            period=self.validated_data.get('period'),
            days_in_period=self.validated_data.get('days_in_period'),
        )
        if not ot.check_days_in_period():
            raise serializers.ValidationError('Перечисленные дни не соответствуют периоду')


class OperationTemplateFilter(FilterSet):
    shop_id = NumberFilter(field_name='operation_type__work_type__shop_id')

    class Meta:
        model = OperationTemplate
        fields = {
            'operation_type_id':['exact', 'in',],
        }


class OperationTemplateViewSet(viewsets.ModelViewSet):
    """

    GET /rest_api/operation_template/
    :params
        shop_id: int, required=False
        operation_type_id: int, required=False
        operation_type_id__in: int,int,... , required=False
    :return [
        {
            'id': 1, 
            'operation_type_id': 1, 
            'tm_start': '10:30:00', 
            'tm_end': '13:00:00', 
            'period': 'M', 
            'days_in_period': [1, 3, 7, 15, 28, 31], 
            'dt_built_to': None, 
            'value': 3.25, 
            'name': 'Ежемесячный', 
            'code': ''
        },        
    ]


    GET /rest_api/operation_template/1/
    :return {
            'id': 1, 
            'operation_type_id': 1, 
            'tm_start': '10:30:00', 
            'tm_end': '13:00:00', 
            'period': 'M', 
            'days_in_period': [1, 3, 7, 15, 28, 31], 
            'dt_built_to': None, 
            'value': 3.25, 
            'name': 'Ежемесячный', 
            'code': ''
    }


    POST /rest_api/operation_template/
    :params
        value: float, required=True
        name: str, required=True
        code: str, required=False
        tm_start: QOS_TIME_FORMAT, required=True
        tm_end: QOS_TIME_FORMAT, required=True
        period: OperationTemplate period, required=True
        days_in_period: IntegerList, required=True
        operation_type_id: int, required=True,
        dt_built_to: QOS_DATE_FORMAT, required=False
    :return 
        code 201
        {
            'id': 1, 
            'operation_type_id': 1, 
            'tm_start': '10:30:00', 
            'tm_end': '13:00:00', 
            'period': 'M', 
            'days_in_period': [1, 3, 7, 15, 28, 31], 
            'dt_built_to': None, 
            'value': 3.25, 
            'name': 'Ежемесячный', 
            'code': ''
        }


    PUT /rest_api/operation_template/1/
    :params
        value: float, required=True
        name: str, required=True
        code: str, required=False
        tm_start: QOS_TIME_FORMAT, required=True
        tm_end: QOS_TIME_FORMAT, required=True
        period: OperationTemplate period, required=True
        days_in_period: IntegerList, required=True
        operation_type_id: int, required=True,
        dt_built_to: QOS_DATE_FORMAT, required=False
        date_rebuild_from: QOS_DATE_FORMAT, required=False
    :return
        {
            'id': 1, 
            'operation_type_id': 1, 
            'tm_start': '10:30:00', 
            'tm_end': '13:00:00', 
            'period': 'M', 
            'days_in_period': [1, 3, 7, 15, 28, 31], 
            'dt_built_to': None, 
            'value': 3.25, 
            'name': 'Ежемесячный', 
            'code': ''
        }


    DELETE /rest_api/operation_template/1/
    :return
        code 204

    """
    permission_classes = [FilteredListPermission]
    filterset_class = OperationTemplateFilter
    serializer_class = OperationTemplateSerializer

    def get_queryset(self):
        return self.filter_queryset(OperationTemplate.objects.filter(dttm_deleted__isnull=True))
    
    def update(self, request, pk=None):
        operation_template = self.get_queryset().get(pk=pk)

        data = OperationTemplateSerializer(instance=operation_template, data=request.data)

        data.is_valid(raise_exception=True)

        date_rebuild_from = data.validated_data.pop('date_rebuild_from', None)

        build_period = False
    
        if operation_template.dt_built_to and \
            (operation_template.value != data.validated_data.get('value')\
            or operation_template.period != data.validated_data.get('period')\
            or operation_template.days_in_period != data.validated_data.get('days_in_period')):
            build_period_clients(operation_template, dt_from=date_rebuild_from, operation='delete')

            build_period = True
        
        data.save()
        

        if build_period:
            build_period_clients(operation_template, dt_from=date_rebuild_from)
        
        return Response(data.data)

    def destroy(self, request, pk=None):
        operation_template = OperationTemplate.objects.get(pk=pk)
        operation_template.delete()
        dt_from = datetime.now().date() + timedelta(days=2)
        build_period_clients(operation_template, dt_from=dt_from, operation='delete')
        return Response(status=status.HTTP_204_NO_CONTENT)

    def create(self, request):
        operation_template = OperationTemplateSerializer(data=request.data)
        operation_template.is_valid(raise_exception=True)
        operation_template.save()
        build_period_clients(operation_template.instance, dt_from=datetime.now().date())
        return Response(status=status.HTTP_201_CREATED, data=operation_template.data)
