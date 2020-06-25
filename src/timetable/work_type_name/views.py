from rest_framework import serializers, viewsets, permissions

from src.timetable.models import WorkTypeName
from src.base.serializers import BaseNetworkSerializer


class WorkTypeNameSerializer(BaseNetworkSerializer):
    name = serializers.CharField(required=False)
    code = serializers.CharField(required=False)
    class Meta:
        model = WorkTypeName
        fields = ['id', 'name', 'code', 'network_id']


class WorkTypeNameViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = WorkTypeNameSerializer

    def get_queryset(self):
        return WorkTypeName.objects.filter(
            dttm_deleted__isnull=True,
            network_id=self.request.user.network_id
        )