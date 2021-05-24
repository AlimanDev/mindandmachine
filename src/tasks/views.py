from datetime import datetime

from django.conf import settings
from django.http.response import Http404
from rest_framework import status
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response

from src.base.permissions import Permission
from src.base.views_abstract import UpdateorCreateViewSet
from .filters import TaskFilter
from .models import Task
from .serializers import TaskSerializer


class TaskViewSet(UpdateorCreateViewSet):
    pagination_class = LimitOffsetPagination
    permission_classes = [Permission]
    serializer_class = TaskSerializer
    filterset_class = TaskFilter
    openapi_tags = ['Task', ]

    def get_queryset(self):
        manager = Task.objects
        if self.action in ['update']:
            manager = Task.objects_with_excluded

        return manager.filter(
            operation_type__shop__network_id=self.request.user.network_id,
        ).select_related(
            'operation_type',
            'operation_type__operation_type_name',
        )

    @staticmethod
    def _parse_dttm_event(dttm_event_str):
        if dttm_event_str:
            return datetime.strptime(dttm_event_str, settings.QOS_DATETIME_FORMAT)

    @classmethod
    def _skip_request(cls, instance: Task, dttm_event: datetime):
        return dttm_event and instance.dttm_event and instance.dttm_event > dttm_event

    def perform_update(self, serializer):
        if self._skip_request(serializer.instance, serializer.validated_data.get('dttm_event')):
            return
        serializer.save(dttm_deleted=None)

    def perform_destroy(self, instance):
        dttm_event = self._parse_dttm_event(self.request.data.get('dttm_event'))
        if self._skip_request(instance, dttm_event):
            return
        instance.dttm_event = dttm_event
        instance.save(update_fields=['dttm_event'])
        instance.delete()

    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Http404:
            return Response({}, status=status.HTTP_200_OK)  # по просьбе Ортеки шлем 200
        self.perform_destroy(instance)
        return Response({}, status=status.HTTP_200_OK)
