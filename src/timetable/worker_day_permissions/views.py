from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.timetable.models import WorkerDayPermission
from .serializers import (
    WorkerDayPermissionSerializer,
    WorkerDayPermissionCurrentUserQueryStringSerializer,
)


class WorkerDayPermissionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = WorkerDayPermissionSerializer

    @action(detail=False, methods=['get'])
    def for_current_user(self, *args, **kwargs):
        """
        GET /rest_api/worker_day_permissions/for_current_user/
        :params
            shop: int, required=True,
            action: (C, U, D, A), required=False,
            graph_type: (F, P), required=False,
        :return [
            {
                "action": "A",
                "graph_type": "F",
                "wd_type": "W"
            },
            ...
        ]
        """
        s = WorkerDayPermissionCurrentUserQueryStringSerializer(
            data=self.request.query_params,
            context=self.get_serializer_context(),
        )
        s.is_valid(raise_exception=True)
        worker_day_permissions_qs = WorkerDayPermission.objects.filter(
            group__in=self.request.user.get_group_ids(s.validated_data['shop'].network, s.validated_data['shop']),
        )
        if s.validated_data.get('action'):
            worker_day_permissions_qs = worker_day_permissions_qs.filter(action=s.validated_data.get('action'))
        if s.validated_data.get('graph_type'):
            worker_day_permissions_qs = worker_day_permissions_qs.filter(graph_type=s.validated_data.get('graph_type'))
        s = self.get_serializer(instance=worker_day_permissions_qs, many=True)
        return Response(s.data)
