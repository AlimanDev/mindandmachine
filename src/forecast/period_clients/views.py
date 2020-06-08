from datetime import datetime, timedelta, time
from rest_framework import serializers, viewsets, status
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from django_filters import DateFilter, NumberFilter
from src.util.utils import JsonResponse
from src.base.permissions import FilteredListPermission
from src.forecast.models import OperationType, PeriodClients, PeriodDemandChangeLog
from django.db.models import Q, F, Sum
from src.conf.djconfig import QOS_DATETIME_FORMAT, QOS_DATE_FORMAT
from rest_framework.decorators import action
from src.base.models import Shop, Employment, FunctionGroup
from src.util.models_converter import Converter
from src.forecast.load_template.utils import apply_reverse_formula # чтобы тесты не падали
from src.forecast.period_clients.utils import upload_demand_util, download_demand_xlsx_util
from src.util.upload import get_uploaded_file


# Serializers define the API representation.
class PeriodClientsDeleteSerializer(serializers.Serializer):
    from_dttm = serializers.DateTimeField(format=QOS_DATETIME_FORMAT, write_only=True)
    to_dttm = serializers.DateTimeField(format=QOS_DATETIME_FORMAT, write_only=True)
    shop_id = serializers.IntegerField()
    operation_type_id = serializers.ListField(required=False, allow_empty=True, child=serializers.IntegerField(), write_only=True)
    type = serializers.CharField()


class PeriodClientsUpdateSerializer(PeriodClientsDeleteSerializer):
    multiply_coef = serializers.FloatField(required=False)
    set_value = serializers.FloatField(required=False)

    def is_valid(self, *args, **kwargs):
        super(PeriodClientsUpdateSerializer, self).is_valid(*args, **kwargs)

        if self.validated_data.get('from_dttm') > self.validated_data.get('to_dttm'):
            raise serializers.ValidationError('Дата начала не может быть больше даты окончания')

        if self.validated_data.get('from_dttm') < datetime.now() and \
            (self.validated_data.get('type') is 'L' or self.validated_data.get('type') is 'S'):
            raise serializers.ValidationError('Нельзя изменить прогноз спроса за прошлый период')


class PeriodClientsSerializer(serializers.ModelSerializer):
    dttm_forecast = serializers.DateTimeField(format=QOS_DATETIME_FORMAT, read_only=True)
    class Meta:
        model = PeriodClients
        fields = ['dttm_forecast', 'value']


class PeriodClientsCreateSerializer(serializers.Serializer):
    data = serializers.JSONField(write_only=True)


class UploadSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    file = serializers.FileField()


class DownloadSerializer(serializers.Serializer):
    dt_from = serializers.DateField(format=QOS_DATE_FORMAT)
    dt_to = serializers.DateField(format=QOS_DATE_FORMAT)
    shop_id = serializers.IntegerField()


class PeriodClientsFilter(FilterSet):
    shop_id = NumberFilter(field_name='operation_type__shop_id')
    work_type_id = NumberFilter(field_name='operation_type__work_type_id')
    dt_from = DateFilter(field_name='dttm_forecast', lookup_expr='date__gte')
    dt_to = DateFilter(field_name='dttm_forecast', lookup_expr='date__lte')

    class Meta:
        model = PeriodClients
        fields = {
            'operation_type_id':['exact', 'in',],
            'type': ['exact',],
        }


class PeriodClientsViewSet(viewsets.ModelViewSet):
    """

    GET /rest_api/period_clients/
    :params
        shop_id: int, required=True,
        dt_from: QOS_DATE_FORMAT, required=True,
        dt_to: QOS_DATE_FORMAT, required=True,
        type: (L, F, S), required=True,
        operation_type_id: int, required=False,
        operation_type_id__in: int,int,... , required=False,
    :return [
        {
            "dttm_forecast":2020-01-01T00:00:00, 
            "value": 2.0,
            
        },
        ...
        {
            "dttm_forecast":2020-01-03T23:00:00, 
            "value": 2.0,
            
        },
    ]


    GET /rest_api/period_clients/indicators/
    :params
        shop_id: int, required=True,
        dt_from: QOS_DATE_FORMAT, required=True,
        dt_to: QOS_DATE_FORMAT, required=True,
        type: (L, F, S), required=True,
        operation_type_id: int, required=False,
        operation_type_id__in: int,int,... , required=False,
        work_type_id: int, requred=False,
    :return {
        "overall_operations": 255.3, 
        "fact_overall_operations": 240.8,
    }


    POST /rest_api/period_clietns/
    :params
        data: JSON, required=True,
    :return 
        code=201

    PUT /rest_api/period_clietns/put/
    :params
        operation_type_id: list(int), requeired=False,
        from_dttm: QOS_DATETIME_FORMAT, required=True,
        to_dttm: QOS_DATETIME_FORMAT, required=True,
        shop_id: int, required=True,
        type: (L, F, S), required=True,
        multiply_coef: float, required=False,
        set_value: float, required=False
    :return
        code=200


    DELETE /rest_api/period_Clients/delete/
    :params
        operation_type_id: list(int), requeired=False,
        from_dttm: QOS_DATETIME_FORMAT, required=True,
        to_dttm: QOS_DATETIME_FORMAT, required=True,
        shop_id: int, required=True,
        type: (L, F, S), required=True
    :return
        code=204

    """
    permission_classes = [FilteredListPermission]
    filterset_class = PeriodClientsFilter
    serializer_class = PeriodClientsSerializer

    def get_queryset(self):
        return self.filter_queryset(PeriodClients.objects.all())

    def create(self, request):
        models_list = []
        data = PeriodClientsCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data = data.validated_data['data']

        shop = Shop.objects.get(id=data['shop_id'])
        dt_from = Converter.parse_date(data['dt_from'])
        dt_to = Converter.parse_date(data['dt_to'])
        type = data.get('type', PeriodClients.LONG_FORECASE_TYPE)

        PeriodClients.objects.select_related('operation_type__work_type').filter(
            type=type,
            dttm_forecast__date__gte=dt_from,
            dttm_forecast__date__lte=dt_to,
            operation_type__shop_id=shop.id,
            operation_type__do_forecast=OperationType.FORECAST,
        ).delete()
        
        for period_demand_value in data['demand']:
            clients = period_demand_value['value']
            clients = 0 if clients < 0 else clients
            models_list.append(
                PeriodClients(
                    type=type,
                    dttm_forecast=Converter.parse_datetime(period_demand_value['dttm']),
                    operation_type_id=period_demand_value['work_type'],
                    value=clients,
                )
            )
        PeriodClients.objects.bulk_create(models_list)
        employments = Employment.objects.filter(
            function_group__allowed_functions__func='set_demand',
            function_group__allowed_functions__access_type__in=[FunctionGroup.TYPE_SHOP, FunctionGroup.TYPE_SUPERSHOP],
            shop=shop,
        ).values_list('user_id', flat=True)

        # notify4users = User.objects.filter(
        #     id__in=employments
        # )

        # Event.objects.mm_event_create(
        #     notify4users,
        #     text='Cоставлен новый спрос на период с {} по {}'.format(data['dt_from'], data['dt_to']),
        #     department=shop,
        # )

        return Response(status=status.HTTP_201_CREATED)
    
    @action(detail=False, methods=['put'])
    def put(self, request, pk=None):
        data = PeriodClientsUpdateSerializer(data=request.data)

        data.is_valid(raise_exception=True)

        models = []

        operation_type_ids = data.validated_data.get('operation_type_id', [])
        dttm_from = data.validated_data.get('from_dttm')
        dttm_to = data.validated_data.get('to_dttm')
        multiply_coef = data.validated_data.get('multiply_coef')
        set_value = data.validated_data.get('set_value')
        shop_id = data.validated_data.get('shop_id')
        type = data.validated_data.get('type')
        if not len(operation_type_ids):
            operation_type_ids = OperationType.objects.select_related(
                'work_type'
            ).filter(
                dttm_added__gte=dttm_from,
                dttm_added__lte=dttm_to,
                dttm_deleted__isnull=True,
                work_type__shop_id=shop_id,
            ).values_list('id', flat=True)

        period_clients = PeriodClients.objects.select_related(
            'operation_type__work_type'
        ).filter(
            operation_type__shop_id=shop_id,
            type=type,
            dttm_forecast__time__gte=dttm_from.time(),
            dttm_forecast__time__lte=dttm_to.time(),
            dttm_forecast__date__gte=dttm_from.date(),
            dttm_forecast__date__lte=dttm_to.date(),
            operation_type_id__in=operation_type_ids
        )

        if (set_value is not None):
            dttm_step = timedelta(seconds=Shop.objects.get(id=shop_id).system_step_in_minutes() * 60)
            dates_needed = set()
            '''
            Создаем множество с нужными датами
            '''
            time_from = dttm_from.time()
            time_to = dttm_to.time()
            for date in range(int(dttm_from.timestamp()), int(dttm_to.timestamp()) + 1, int(timedelta(days=1).total_seconds())):
                date = datetime.fromtimestamp(date)
                date_from = datetime.combine(date, time_from)
                date_to = datetime.combine(date, time_to)
                dates_needed = dates_needed | {datetime.fromtimestamp(date) \
                    for date in range(int(date_from.timestamp()), int(date_to.timestamp()), dttm_step.seconds)}
            '''
            Проходимся по всем операциям, для каждой операции получаем множетсво дат, которые уже
            указаны. Затем вычитаем из множества с нужными датами множество дат, которые уже есть.
            Потом итерируемся по резальтирующему множеству и для каждого элемента создаем PeriodClient
            с нужной датой, операцией и значением.
            '''
            for o_id in operation_type_ids:
                dates_to_add = set(period_clients.filter(operation_type_id=o_id).values_list('dttm_forecast', flat=True))
                dates_to_add = dates_needed.difference(dates_to_add)
                for date in dates_to_add:
                        models.append(
                            PeriodClients(
                                dttm_forecast=date, 
                                operation_type_id=o_id, 
                                value=set_value,
                                type=type,
                            )
                        )
        PeriodClients.objects.bulk_create(models)
        period_clients.update(value=set_value if set_value else F('value')*multiply_coef)
        changed_operation_type_ids = set(period_clients.values_list('operation_type_id', flat=True))
        if Shop.objects.filter(pk=shop_id, load_template__isnull=False).exists():
            for o_type in OperationType.objects.select_related('shop').filter(id__in=operation_type_ids):
                apply_reverse_formula(
                    o_type, 
                    dt_from=dttm_from.date(), 
                    dt_to=dttm_to.date(), 
                    tm_from=dttm_from.time(), 
                    tm_to=dttm_to.time(),
                    lang=request.user.lang,
                )
        for x in changed_operation_type_ids:
            PeriodDemandChangeLog.objects.create(
                dttm_from=dttm_from,
                dttm_to=dttm_to,
                operation_type_id=x,
                multiply_coef=multiply_coef,
                set_value=set_value
            )

        return Response(status=200)

    @action(detail=False, methods=['delete'])
    def delete(self, request, pk=None):
        data = PeriodClientsDeleteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        operation_type_ids = data.validated_data.get('operation_type_id', [])
        if not operation_type_ids:
            return JsonResponse.value_error('Operation type id should be defined')
        dttm_from = data.validated_data.get('from_dttm')
        dttm_to = data.validated_data.get('to_dttm')
        shop_id = data.validated_data.get('shop_id')
        type = data.validated_data.get('type')
        PeriodClients.objects.filter(
            operation_type__shop_id=shop_id,
            type=type,
            dttm_forecast__date__gte=dttm_from.date(),
            dttm_forecast__date__lte=dttm_to.date(),
            dttm_forecast__time__gte=dttm_from.time(),
            dttm_forecast__time__lte=dttm_to.time(),
            operation_type_id__in=operation_type_ids,
        ).delete()
        return Response(status=204)

    def list(self, requset):
        data = self.get_queryset().values('dttm_forecast', 'type').annotate(
            value=Sum('value'),
        )
        return Response(PeriodClientsSerializer(data, many=True).data)

    @action(detail=False, methods=['get'])
    def indicators(self, request):
        clients = self.get_queryset().select_related(
            'operation_type',
            'operation_type__work_type'
        )
        long_type_clients = clients.filter(type=PeriodClients.LONG_FORECASE_TYPE).aggregate(Sum('value'))['value__sum']
        fact_type_clients = clients.filter(type=PeriodClients.FACT_TYPE).aggregate(Sum('value'))['value__sum']
        # prev_clients = PeriodClients.objects.select_related(
        #     'operation_type__work_type'
        # ).filter(
        #     operation_type__work_type__shop_id=shop_id,
        #     operation_type__work_type_id__in=work_type_filter_list,
        #     dttm_forecast__gte=datetime.combine(dt_from, time()) - relativedelta(months=1),
        #     dttm_forecast__lt=datetime.combine(dt_to, time()) - relativedelta(months=1),
        #     type=PeriodClients.LONG_FORECASE_TYPE,
        # ).aggregate(Sum('value'))['value__sum']

        # if long_type_clients and prev_clients and prev_clients != 0:
        #     growth = (long_type_clients - prev_clients) / prev_clients * 100
        # else:
        #     growth = None

        return Response({
            'overall_operations': long_type_clients / 1000 if long_type_clients else None,  # в тысячах
            # 'operations_growth': growth,
            'fact_overall_operations': fact_type_clients / 1000 if fact_type_clients else None,
        })


    @action(detail=False, methods=['post'])
    @get_uploaded_file
    def upload(self, request, file):
        data = UploadSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return upload_demand_util(file, data.validated_data['shop_id'], lang=request.user.lang)


    @action(detail=False, methods=['get'])
    def download(self, request):
        data = DownloadSerializer(data=request.query_params)
        data.is_valid(raise_exception=True)
        return download_demand_xlsx_util(request, data.validated_data)
