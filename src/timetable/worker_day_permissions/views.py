from rest_framework.generics import GenericAPIView
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from src.timetable.models import GroupWorkerDayPermission
from .serializers import (
    GroupWorkerDayPermissionSerializer,
    WorkerDayPermissionQueryStringSerializer,
)


class WorkerDayPermissionsAPIView(RetrieveModelMixin, GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = GroupWorkerDayPermissionSerializer

    def get(self, *args, **kwargs):
        """
        GET /rest_api/worker_day_permissions/
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
        s = WorkerDayPermissionQueryStringSerializer(
            data=self.request.query_params,
            context=self.get_serializer_context(),
        )
        s.is_valid(raise_exception=True)
        groups_wd_perms_qs = GroupWorkerDayPermission.objects.filter(
            group__in=self.request.user.get_group_ids(s.validated_data['shop'].network, s.validated_data['shop']),
        )
        if s.validated_data.get('action'):
            groups_wd_perms_qs = groups_wd_perms_qs.filter(
                worker_day_permission__action=s.validated_data.get('action'))
        if s.validated_data.get('graph_type'):
            groups_wd_perms_qs = groups_wd_perms_qs.filter(
                worker_day_permission__graph_type=s.validated_data.get('graph_type'))
        s = self.get_serializer(instance=groups_wd_perms_qs, many=True)
        return Response(s.data)
