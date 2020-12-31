import datetime
from rest_framework import serializers, viewsets, mixins
from src.base.permissions import FilteredListPermission
from rest_framework.response import Response
from src.conf.djconfig import QOS_DATE_FORMAT
from src.timetable.models import ShopMonthStat
from django_filters.rest_framework import FilterSet
from rest_framework.validators import UniqueTogetherValidator
from rest_framework.decorators import action
from drf_yasg.utils import swagger_auto_schema


# Serializers define the API representation.
class ShopMonthStatSerializer(serializers.ModelSerializer):
    dt = serializers.DateField(format=QOS_DATE_FORMAT, read_only=True)
    class Meta:
        model = ShopMonthStat
        fields = ['id', 'shop_id', 'status_message', 'dt', 'status', 'fot', 'lack', 'idle', 'workers_amount', 'revenue', 'fot_revenue']
        validators = [
            UniqueTogetherValidator(
                queryset=ShopMonthStat.objects.all(),
                fields=['shop_id', 'dt'],
            ),
        ]


class StatusSerializer(serializers.Serializer):
    dt = serializers.DateField(format=QOS_DATE_FORMAT)
    shop_id = serializers.IntegerField()


class ShopMonthStatFilter(FilterSet):
    class Meta:
        model = ShopMonthStat
        fields = {
            'shop_id': ['exact', 'in'],
            'dt': ['exact', 'in'],
        }


class ShopMonthStatViewSet(mixins.UpdateModelMixin,
                                mixins.ListModelMixin,
                                mixins.RetrieveModelMixin,
                                viewsets.GenericViewSet):
    """

    GET /rest_api/shop_month_stat/
    :return [   
        {
            'id': 1, 
            'shop_id': 1, 
            'status_message': '', 
            'dt': '2020-02-20', 
            'status': 'R', 
            'fot': 20000, 
            'lack': 10, 
            'idle': 2, 
            'workers_amount': 10, 
            'revenue': 67, 
            'fot_revenue': 11,
        },
        ...
    ]


    GET /rest_api/shop_month_stat/6/
    :return {
        'id': 6, 
        'shop_id': 2, 
        'status_message': '', 
        'dt': '2020-02-20', 
        'status': 'R', 
        'fot': 20000, 
        'lack': 10, 
        'idle': 2, 
        'workers_amount': 10, 
        'revenue': 67, 
        'fot_revenue': 11,
    }

    """
    permission_classes = [FilteredListPermission]
    serializer_class = ShopMonthStatSerializer
    queryset = ShopMonthStat.objects.filter(shop__dttm_deleted__isnull=True)
    http_method_names = ['get', 'put']
    openapi_tags = ['ShopMonthStat',]


    @swagger_auto_schema(
        query_serializer=StatusSerializer, 
        responses={200:ShopMonthStatSerializer},
        operation_description='''
        Метод для получения статуса расписания по магазину
        ''',
    )
    @action(detail=False, methods=['get',])
    def status(self, request):
        data = StatusSerializer(data=request.query_params)
        data.is_valid(raise_exception=True)
        dt = data.validated_data['dt'].replace(day=1)
        try:
            shop_stat = ShopMonthStat.objects.get(
                shop_id=data.validated_data['shop_id'],
                dt=dt,
            )
            res = ShopMonthStatSerializer(shop_stat).data
        except:
            res = {'status': None}

        return Response(res)

