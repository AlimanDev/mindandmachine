from rest_framework import serializers, permissions
from rest_framework.pagination import LimitOffsetPagination
from src.apps.forecast.models import OperationTypeName
from src.interfaces.api.serializers.base import BaseNetworkSerializer
from src.interfaces.api.views.base import BaseActiveNamedModelViewSet
from django_filters.rest_framework import BooleanFilter
from django.utils.translation import gettext as _
from src.apps.base.filters import BaseActiveNamedModelFilter


class OperationTypeNameSerializer(BaseNetworkSerializer):
    name = serializers.CharField(required=False)
    code = serializers.CharField(required=False)
    work_type_name_id = serializers.IntegerField(read_only=True) # привязка только при создании work_type_name

    class Meta:
        model = OperationTypeName
        fields = ['id', 'name', 'code', 'network_id', 'work_type_name_id', 'do_forecast']

    
    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        exclude_filter = {}
        if self.instance:
            exclude_filter['pk'] = self.instance.id
        self.validated_data['code'] = None if self.validated_data.get('code') == '' else self.validated_data.get('code')
        if self.validated_data.get('code') and OperationTypeName.objects.filter(code=self.validated_data.get('code')).exclude(**exclude_filter).exists():
            raise serializers.ValidationError(_('Name with code {code} already exists.').format(code=self.validated_data.get('code')))
        
        if OperationTypeName.objects.filter(name=self.validated_data.get('name')).exclude(**exclude_filter).exists():
            raise serializers.ValidationError(_('The name {name} is already in the system').format(name=self.validated_data.get('name')))

        return True


class OperationTypeNameFilter(BaseActiveNamedModelFilter):

    no_work_type = BooleanFilter(field_name='work_type_name_id', lookup_expr='isnull')

    class Meta:
        model = OperationTypeName
        fields = {
            'do_forecast': ['exact', ]
        }


class OperationTypeNameViewSet(BaseActiveNamedModelViewSet):
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
    filterset_class = OperationTypeNameFilter
    openapi_tags = ['OperationTypeName',]

    def get_queryset(self):
        return OperationTypeName.objects.filter(
            network_id=self.request.user.network_id,
            dttm_deleted__isnull=True)

