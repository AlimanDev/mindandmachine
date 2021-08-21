from rest_framework.viewsets import ModelViewSet

from src.base.permissions import Permission
from .serializers import WorkerDayTypeSerializer
from ..models import WorkerDayType


class WorkerDayTypeViewSet(ModelViewSet):
    serializer_class = WorkerDayTypeSerializer
    permission_classes = [Permission]
    openapi_tags = ['WorkerDayType', ]

    def get_queryset(self):
        return WorkerDayType.objects
