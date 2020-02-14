import datetime

from rest_framework import serializers, viewsets
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
from django_filters import NumberFilter
from src.util.utils import JsonResponse
from src.base.permissions import FilteredListPermission
from src.forecast.models import OperationType, OperationTypeName
from django.db.models import Q, F
from src.forecast.operation_type_name.views import OperationTypeNameSerializer

# Serializers define the API representation.
class OperationTypeSerializer(serializers.ModelSerializer):
    operation_type_name = OperationTypeNameSerializer(required=False)
    work_type_id = serializers.IntegerField(required=False)
    code = serializers.CharField(required=False, write_only=True)
    operation_type_name_id = serializers.IntegerField(write_only=True, required=False)
    class Meta:
        model = OperationType
        fields = ['id', 'work_type_id', 'speed_coef', 'do_forecast', 'operation_type_name', 'code', 'operation_type_name_id']


class OperationTypeFilter(FilterSet):
    shop_id = NumberFilter(field_name='work_type__shop_id')
    class Meta:
        model = OperationType
        fields = {
            'work_type_id':['exact', 'in',],
            'id':['exact', 'in',],
        }


class OperationTypeViewSet(viewsets.ModelViewSet):
    """

    GET /rest_api/operation_type/
    :params
        shop_id: int, required=False
        work_type_id: int, required=False
        work_type_id__in: int, int, ..., required=False
        id: int, required=False
        id__in: int, int, ..., required=False
    :return [
        {
            "id":2,
            "operation_type_name": {
                "id": 1,
                "name": "abcd",
                "code": '2',
            },
            "work_type_id": 1,
            "speed_coef": 3.0,
            "do_forecast": "H"
        },
        ...
    ]


    GET /rest_api/operation_type/6/
    :return {
        "id":6,
        "operation_type_name": {
            "id": 2,
            "name": "abcde",
            "code": '4',
        },
        "work_type_id": 1,
        "speed_coef": 3.0,
        "do_forecast": "H"
    }


    POST /rest_api/operation_type/
    :params
        work_type_id: int, required=True
        operation_type_name_id: int, required=False
        code: str, required=False
        speed_coef: float, required=True
        do_forecast: OperationType do_forecast, required=False
    :return 
        code 201
        {
            "id":6,
            "operation_type_name": {
                "id": 2,
                "name": "abcde",
                "code": '4',
            },
            "work_type_id": 1,
            "speed_coef": 3.0,
            "do_forecast": "H"
        }


    PUT /rest_api/operation_type/6/
    :params
        work_type_id: int, required=False
        operation_type_name_id: int, required=False
        code: str, required=False
        speed_coef: float, required=False
        do_forecast: OperationType do_forecast, required=False
    :return {
        "id":6,
        "operation_type_name": {
            "id": 2,
            "name": "abcde",
            "code": '4',
        },
        "work_type_id": 1,
        "speed_coef": 3.0,
        "do_forecast": "H"
    }


    DELETE /rest_api/operation_type/6/
    :return
        code 204

    """
    permission_classes = [FilteredListPermission]
    serializer_class = OperationTypeSerializer
    filterset_class = OperationTypeFilter

    def get_queryset(self):
        return self.filter_queryset(
            OperationType.objects.select_related('operation_type_name').filter(dttm_deleted__isnull=True)
        )