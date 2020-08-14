from rest_framework import serializers, viewsets, permissions
from rest_framework.pagination import LimitOffsetPagination

from src.timetable.models import WorkTypeName
from src.base.serializers import BaseNetworkSerializer
from src.base.exceptions import MessageError
from src.base.views import BaseActiveNamedModelViewSet


class WorkTypeNameSerializer(BaseNetworkSerializer):
    name = serializers.CharField(required=False)
    code = serializers.CharField(required=False)
    class Meta:
        model = WorkTypeName
        fields = ['id', 'name', 'code', 'network_id']
    
    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        exclude_filter = {}
        if self.instance:
            exclude_filter['pk'] = self.instance.id
        self.validated_data['code'] = None if self.validated_data.get('code') == '' else self.validated_data.get('code')
        if self.validated_data.get('code') and WorkTypeName.objects.filter(code=self.validated_data.get('code')).exclude(**exclude_filter).exists():
            raise MessageError('unique_name_code', params={'code': self.validated_data.get('code')}, lang=self.context['request'].user.lang)
        
        if WorkTypeName.objects.filter(name=self.validated_data.get('name')).exclude(**exclude_filter).exists():
            raise MessageError('unique_name_name', params={'name': self.validated_data.get('name')}, lang=self.context['request'].user.lang)

        return True


class WorkTypeNameViewSet(BaseActiveNamedModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WorkTypeNameSerializer
    pagination_class = LimitOffsetPagination

    def get_queryset(self):
        return WorkTypeName.objects.filter(
            dttm_deleted__isnull=True,
            network_id=self.request.user.network_id
        )