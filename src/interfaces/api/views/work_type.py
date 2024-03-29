from datetime import datetime

from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from django_filters.rest_framework import FilterSet, CharFilter
from drf_yasg.utils import swagger_auto_schema
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.validators import UniqueTogetherValidator

from src.apps.base.permissions import Permission
from src.interfaces.api.serializers.base import ModelSerializerWithCreateOnlyFields
from src.apps.base.views_abstract import BaseModelViewSet
from src.conf.djconfig import QOS_DATE_FORMAT
from src.apps.timetable.models import WorkType, WorkTypeName
from src.apps.timetable.work_type.utils import ShopEfficiencyGetter
from src.common.openapi.responses import efficieny_response_schema_dict as response_schema_dict


# Serializers define the API representation.
class WorkTypeSerializer(ModelSerializerWithCreateOnlyFields):
    code = serializers.CharField(required=False, write_only=True)
    shop_id = serializers.IntegerField(required=False)
    work_type_name_id = serializers.IntegerField(required=False)
    class Meta:
        model = WorkType
        fields = ['id', 'priority', 'dttm_last_update_queue', 'min_workers_amount', 'max_workers_amount',\
             'probability', 'prior_weight', 'shop_id', 'code', 'work_type_name_id', 'preliminary_cost_per_hour']
        create_only_fields = ['work_type_name_id']
        validators = [
            UniqueTogetherValidator(
                queryset=WorkType.objects.filter(dttm_deleted__isnull=True),
                fields=['shop_id', 'work_type_name_id'],
            ),
        ]
    
    def to_internal_value(self, data):
        if data.get('code', False) and not self.instance:
            data['work_type_name_id'] = WorkTypeName.objects.get(code=data.get('code')).id   
        return super().to_internal_value(data)


class EfficiencySerializer(serializers.Serializer):
    from_dt = serializers.DateField(format=QOS_DATE_FORMAT)
    to_dt = serializers.DateField(format=QOS_DATE_FORMAT)
    work_type_ids = serializers.ListField(
        allow_empty=True, child=serializers.IntegerField(), required=False, default=[])
    shop_id = serializers.IntegerField()
    graph_type = serializers.ChoiceField(
        default='plan_approved', label='Тип графика',
        choices=['plan_edit', 'plan_approved', 'fact_approved', 'fact_edit'],
    )
    efficiency = serializers.BooleanField(default=True)
    indicators = serializers.BooleanField(default=False)

    def is_valid(self, *args, **kwargs):
        super(EfficiencySerializer, self).is_valid(*args, **kwargs)

        if self.validated_data['from_dt'] > self.validated_data['to_dt']:
            raise serializers.ValidationError(_('Date start should be less then date end'))


class WorkTypeFilter(FilterSet):
    shop_id__in = CharFilter(method='shop_id__in_filter',)

    def shop_id__in_filter(self, queryset, name, value):
        if value:
            value = value.split(',')
            queryset = queryset.filter(shop_id__in=value)
        return queryset

    class Meta:
        model = WorkType
        fields = {
            'shop_id':['exact',],
        }


class WorkTypeViewSet(BaseModelViewSet):
    """

    GET /rest_api/work_type/
    :params
        shop_id: int, required=False
    :return [
        {
            "id": 2,
            "priority": 23,
            "dttm_last_update_queue": None,
            "min_workers_amount": 2,
            "max_workers_amount": 10,
            "probability": 2.0,
            "prior_weigth": 1.0,
            "shop_id": 1,
            "work_type_name":{
                "id": 1,
                "name": "Work type",
                "code": "1",
            }
        },
        ...
    ]


    GET /rest_api/work_type/6/
    :return {
        "id": 6,
        "priority": 23,
        "dttm_last_update_queue": None,
        "min_workers_amount": 2,
        "max_workers_amount": 10,
        "probability": 2.0,
        "prior_weigth": 1.0,
        "shop_id": 1,
        "work_type_name":{
            "id": 1,
            "name": "Work type",
            "code": "1",
        }
    }


    POST /rest_api/work_type/
    :params
        priority: int, required=False
        min_workers_amount: int, required=False
        max_workers_amount: int, required=False
        probability: float, required=Fasle
        prior_weigth: float, required=False
        shop_id: int, required=True
        code: str, required=False
        work_type_name_id: int, required=False
    :return 
        code 201
        {
            "id": 6,
            "priority": 23,
            "dttm_last_update_queue": None,
            "min_workers_amount": 2,
            "max_workers_amount": 10,
            "probability": 2.0,
            "prior_weigth": 1.0,
            "shop_id": 1,
            "work_type_name":{
                "id": 1,
                "name": "Work type",
                "code": "1",
            }
        }


    PUT /rest_api/work_type/6/
    :params
        priority: int, required=False
        min_workers_amount: int, required=False
        max_workers_amount: int, required=False
        probability: float, required=Fasle
        prior_weigth: float, required=False
        shop_id: int, required=True
        code: str, required=False
        work_type_name_id: int, required=False
    :return {
        "id": 6,
        "priority": 23,
        "dttm_last_update_queue": None,
        "min_workers_amount": 2,
        "max_workers_amount": 10,
        "probability": 2.0,
        "prior_weigth": 1.0,
        "shop_id": 1,
        "work_type_name":{
            "id": 1,
            "name": "Work type",
            "code": "1",
        }
    }


    DELETE /rest_api/work_type/6/
    :return
        code 204

    """
    permission_classes = [Permission]
    serializer_class = WorkTypeSerializer
    filterset_class = WorkTypeFilter
    openapi_tags = ['WorkType',]

    def get_queryset(self):
        return self.filter_queryset(
            WorkType.objects.filter(
                Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gte=datetime.now()),
            )
        )

    @swagger_auto_schema(
        query_serializer=EfficiencySerializer,
        operation_description='Возвращает нагрузку',
        responses=response_schema_dict,
    )
    @action(detail=False, methods=['get'], filterset_class=None)
    def efficiency(self, request):
        data = EfficiencySerializer(data=request.query_params)

        data.is_valid(raise_exception=True)

        return Response(ShopEfficiencyGetter(
            **data.validated_data,
        ).get(), status=200)
