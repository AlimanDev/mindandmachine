import datetime

from rest_framework import serializers, viewsets, permissions
from rest_framework.response import Response
from src.util.utils import JsonResponse
from src.forecast.models import OperationTypeName, OperationType

# Serializers define the API representation.
class OperationTypeNameSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=False)
    code = serializers.CharField(required=False)
    class Meta:
        model = OperationTypeName
        fields = ['id', 'name', 'code']


class OperationTypeNameViewSet(viewsets.ModelViewSet):
    """

    GET /rest_api/work_type_name/
    :return [   {"id": 1, "title": Abcd, "code": "1"}
        {"id": 2, "title": Aaaa, "code": "2"}, ...
    ]

    GET /rest_api/work_type_name/6/
    :return {"id": 6, ...}


    POST /rest_api/work_type_name/, {"title": 'abcd'}
    :return {"id": 10, ...}

    PUT /rest_api/work_type_name/6, {"title": 'abcd'}
    :return {"id": 6, ...}

    Note:
    Если код не нужен с фронта отправлять code: null

    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OperationTypeNameSerializer
    queryset = OperationTypeName.objects.filter(dttm_deleted__isnull=True)

