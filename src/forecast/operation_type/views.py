import datetime

from rest_framework import serializers, viewsets
from rest_framework.response import Response
from django_filters.rest_framework import FilterSet
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
    class Meta:
        model = OperationType
        fields = {
            'work_type__shop_id':['exact',],
            'work_type_id':['exact', 'in',],
            'id':['exact', 'in',],
        }


class OperationTypeViewSet(viewsets.ModelViewSet):
    """

    GET /rest_api/operation_type/?shop_id=6
    :return [{"id":2, ...},{"id":3, ...}]

    GET /rest_api/operation_type/
    :return [   {"id": 1, ...}
        {"id": 2, ...}, ...
    ]

    GET /rest_api/operation_type/6/
    :return {"id": 6, ...}


    POST /rest_api/operation_type/, {"operation_type_name_id": 1}
    :return {"id": 10, ...}

    PUT /rest_api/operation_type/6, {"operation_type_name_id": 1}
    :return {"id": 6, ...}

    """
    permission_classes = [FilteredListPermission]
    serializer_class = OperationTypeSerializer
    filterset_class = OperationTypeFilter

    def get_queryset(self):
        return self.filter_queryset(
            OperationType.objects.select_related('operation_type_name').filter(dttm_deleted__isnull=True)
        )