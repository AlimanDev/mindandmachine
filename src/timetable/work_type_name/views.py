import datetime

from rest_framework import serializers, viewsets, permissions
from rest_framework.response import Response
from src.util.utils import JsonResponse

from src.timetable.models import WorkTypeName, WorkType


# Serializers define the API representation.
class WorkTypeNameSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=False)
    code = serializers.CharField(required=False)
    class Meta:
        model = WorkTypeName
        fields = ['id', 'name', 'code']


class WorkTypeNameViewSet(viewsets.ModelViewSet):
    """

    GET /rest_api/work_type_name/
    :return [   
        {
            "id": 1, 
            "name": "Abcd", 
            "code": "1"
        },
        ...
    ]


    GET /rest_api/work_type_name/6/
    :return {
        "id": 6,
        "name": "Abcde", 
        "code": "6"
    }


    POST /rest_api/work_type_name/
    :params
        name: str, required=True
        code: str, required=False
    :return 
        code 201
        {
            "id": 6,
            "name": "Abcde", 
            "code": "6"
        }


    PUT /rest_api/work_type_name/6/
    :params
        name: str, required=False
        code: str, required=False
    :return {
        "id": 6,
        "name": "Abcde", 
        "code": "6"
    }


    DELETE /rest_api/work_type_name/6/
    :return
        code 204

    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WorkTypeNameSerializer
    queryset = WorkTypeName.objects.filter(dttm_deleted__isnull=True)
