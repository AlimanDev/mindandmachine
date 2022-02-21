from rest_framework.validators import UniqueTogetherValidator
from rest_framework import serializers
from django_filters.rest_framework import FilterSet
from django_filters import NumberFilter
from django.db.models import Q
from datetime import datetime

from src.base.permissions import FilteredListPermission
from src.base.serializers import ModelSerializerWithCreateOnlyFields
from src.base.views_abstract import BaseModelViewSet
from src.forecast.models import OperationType, OperationTypeName
from src.forecast.operation_type_name.views import OperationTypeNameSerializer


class OperationTypeSerializer(ModelSerializerWithCreateOnlyFields):
    operation_type_name = OperationTypeNameSerializer(read_only=True)
    work_type_id = serializers.IntegerField(read_only=True) # создается только при создании work_type
    code = serializers.CharField(required=False, write_only=True)
    operation_type_name_id = serializers.IntegerField(write_only=True, required=False)
    shop_id = serializers.IntegerField()

    class Meta:
        model = OperationType
        fields = ['id', 'work_type_id', 'operation_type_name', 'code', 'operation_type_name_id', 'shop_id']
        create_only_fields = ['operation_type_name_id']
        validators = [
            UniqueTogetherValidator(
                queryset=OperationType.objects.all(),
                fields=['operation_type_name_id', 'shop_id'],
            ),
        ]

    def to_internal_value(self, data):
        if data.get('code', False) and not self.instance:
            self.initial_data['operation_type_name_id'] = OperationTypeName.objects.get(code=self.initial_data.get('code')).id
        return super().to_internal_value(data)



class OperationTypeFilter(FilterSet):
    shop_id = NumberFilter(field_name='shop_id')
    class Meta:
        model = OperationType
        fields = {
            'work_type_id':['exact', 'in',],
            'id':['exact', 'in',],
        }


class OperationTypeViewSet(BaseModelViewSet):
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
    }


    POST /rest_api/operation_type/
    :params
        work_type_id: int, required=True
        operation_type_name_id: int, required=False
        code: str, required=False
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
        }


    PUT /rest_api/operation_type/6/
    :params
        work_type_id: int, required=False
        operation_type_name_id: int, required=False
        code: str, required=False
    :return {
        "id":6,
        "operation_type_name": {
            "id": 2,
            "name": "abcde",
            "code": '4',
        },
        "work_type_id": 1,
    }


    DELETE /rest_api/operation_type/6/
    :return
        code 204

    """
    permission_classes = [FilteredListPermission]
    serializer_class = OperationTypeSerializer
    filterset_class = OperationTypeFilter
    openapi_tags = ['OperationType',]

    def get_queryset(self):
        return OperationType.objects.select_related('operation_type_name').filter(
            Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gte=datetime.now()),
        )
