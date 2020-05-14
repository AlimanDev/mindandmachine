from rest_framework import serializers, viewsets, permissions
from src.forecast.models import OperationTypeName
from src.base.serializers import BaseNetworkSerializer

class OperationTypeNameSerializer(BaseNetworkSerializer):
    name = serializers.CharField(required=False)
    code = serializers.CharField(required=False)

    class Meta:
        model = OperationTypeName
        fields = ['id', 'name', 'code', 'network_id']


class OperationTypeNameViewSet(viewsets.ModelViewSet):
    """

    GET /rest_api/operation_type_name/
    :return [   
        {
            "id": 1, 
            "name": "Abcd", 
            "code": "1"
        },
        ...
    ]


    GET /rest_api/operation_type_name/6/
    :return {
        "id": 6, 
        "name": "Abcde", 
        "code": "6"
    }


    POST /rest_api/operation_type_name/
    :params
        name: str, required=True,
        code: str, required=False
    :return 
        code 201
        {
            "id": 10,
            "name": "AAAA",
            "code": None,
        }


    PUT /rest_api/operation_type_name/6/
    :params
        name: str, required=False,
        code: str, required=False
    :return 
        {
            "id": 10,
            "name": "AAAA",
            "code": None,
        }

    
    DELETE /rest_api/operation_type_name/6/
    :return
        code 204

    Note:
    Если код не нужен с фронта отправлять code: null

    """
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = OperationTypeNameSerializer
    def get_queryset(self):
        return OperationTypeName.objects.filter(
            network_id=self.request.user.network_id,
            dttm_deleted__isnull=True)

