from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication

from src.base.permissions import FilteredListPermission

from src.timetable.models import WorkerDay, WorkerDayApprove
from src.timetable.serializers import WorkerDaySerializer, WorkerDayReadSerializer, WorkerDayApproveSerializer
from src.timetable.filters import MultiShopsFilterBackend, WorkerDayFilter, WorkerDayApproveFilter

from dateutil.relativedelta import relativedelta

class WorkerDayApproveViewSet(viewsets.ModelViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [FilteredListPermission]
    serializer_class = WorkerDayApproveSerializer
    filterset_class = WorkerDayApproveFilter
    queryset = WorkerDayApprove.objects.all()

    def perform_create(self, serializer):
        #TODO: dt.day=1
        worker_day_approve=serializer.save()
        dt = worker_day_approve.dt_approved
        dt_to = dt + relativedelta(months=1)

        WorkerDay.objects.filter(
            dttm_deleted__isnull=True,
            worker_day_approve_id__isnull=True,
            shop_id=worker_day_approve.shop_id,
            dt__lt=dt_to,
            dt__gte=dt,
        ).update(worker_day_approve_id=worker_day_approve.id)
        return worker_day_approve

    def perform_destroy(self, instance):
        WorkerDay.objects.\
            filter(worker_day_approve=instance).\
            update(worker_day_approve=None)
        instance.delete()


class WorkerDayViewSet(viewsets.ModelViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [FilteredListPermission]
    serializer_class = WorkerDaySerializer
    filterset_class = WorkerDayFilter
    permission_name = 'department'
    queryset = WorkerDay.objects.qos_filter_version(1)
    filter_backends = [MultiShopsFilterBackend]
    # filter_backends = [DjangoFilterBackend]

    def list(self, request,  *args, **kwargs):
        queryset = self.get_queryset()#.qos_filter_version(1)
        queryset = self.filter_queryset(queryset)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
