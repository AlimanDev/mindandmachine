from rest_framework import serializers, viewsets, permissions
from rest_framework.pagination import LimitOffsetPagination
from src.forecast.models import OperationTypeName
from src.base.serializers import BaseNetworkSerializer
from src.base.exceptions import MessageError


class OperationTypeNameSerializer(BaseNetworkSerializer):
    name = serializers.CharField(required=False)
    code = serializers.CharField(required=False)

    class Meta:
        model = OperationTypeName
        fields = ['id', 'name', 'code', 'network_id']

    
    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        self.validated_data['code'] = None if self.validated_data.get('code') == '' else self.validated_data.get('code')
        if self.validated_data.get('code') and OperationTypeName.objects.filter(code=self.validated_data.get('code')).exists():
            raise MessageError('unique_name_code', params={'code': self.validated_data.get('code')}, lang=self.context['request'].user.lang)
        
        if OperationTypeName.objects.filter(name=self.validated_data.get('name')).exists():
            raise MessageError('unique_name_name', params={'name': self.validated_data.get('name')}, lang=self.context['request'].user.lang)

        return True

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
    pagination_class = LimitOffsetPagination
    def get_queryset(self):
        return OperationTypeName.objects.filter(
            network_id=self.request.user.network_id,
            dttm_deleted__isnull=True)

