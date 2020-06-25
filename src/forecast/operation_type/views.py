from rest_framework.validators import UniqueTogetherValidator
from rest_framework import serializers, viewsets
from django_filters.rest_framework import FilterSet
from django_filters import NumberFilter

from src.base.permissions import FilteredListPermission
from src.forecast.models import OperationType, OperationTypeName
from src.forecast.operation_type_name.views import OperationTypeNameSerializer


class OperationTypeSerializer(serializers.ModelSerializer):
    operation_type_name = OperationTypeNameSerializer(required=False)
    work_type_id = serializers.IntegerField(required=False)
    code = serializers.CharField(required=False, write_only=True)
    operation_type_name_id = serializers.IntegerField(write_only=True, required=False)
    shop_id = serializers.IntegerField(required=False)

    class Meta:
        model = OperationType
        fields = ['id', 'work_type_id', 'do_forecast', 'operation_type_name', 'code', 'operation_type_name_id', 'shop_id']
        validators = [
            UniqueTogetherValidator(
                queryset=OperationType.objects.all(),
                fields=['operation_type_name_id', 'shop_id'],
            ),
        ]

    def is_valid(self, *args, **kwargs):
        if self.initial_data.get('code', False):
            self.initial_data['operation_type_name_id'] = OperationTypeName.objects.get(code=self.initial_data.get('code')).id
        super().is_valid(*args, **kwargs)


class OperationTypeFilter(FilterSet):
    shop_id = NumberFilter(field_name='shop_id')
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
        "do_forecast": "H"
    }


    POST /rest_api/operation_type/
    :params
        work_type_id: int, required=True
        operation_type_name_id: int, required=False
        code: str, required=False
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
            "do_forecast": "H"
        }


    PUT /rest_api/operation_type/6/
    :params
        work_type_id: int, required=False
        operation_type_name_id: int, required=False
        code: str, required=False
        do_forecast: OperationType do_forecast, required=False
    :return {
        "id":6,
        "operation_type_name": {
            "id": 2,
            "name": "abcde",
            "code": '4',
        },
        "work_type_id": 1,
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
        return OperationType.objects.select_related('operation_type_name').filter(
                dttm_deleted__isnull=True
        )