from rest_framework import viewsets, mixins
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication

from src.base.permissions import FilteredListPermission

from src.timetable.models import WorkerDay, WorkerDayApprove
from src.timetable.serializers import WorkerDaySerializer, WorkerDayApproveSerializer
from src.timetable.filters import MultiShopsFilterBackend, WorkerDayFilter, WorkerDayApproveFilter

from dateutil.relativedelta import relativedelta


class WorkerDayApproveViewSet(
    viewsets.GenericViewSet,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
):

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
        ).update(
            worker_day_approve_id=worker_day_approve.id
        )
        WorkerDay.objects.filter(
            child__worker_day_approve_id=worker_day_approve.id
        ).delete()
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

    def perform_update(self, serializer):
        #TODO: псевдокод

        # Если подтвержденная версия, создаем новую, сославшись на старую
        if serializer.instance.worker_day_approve_id:
            data = serializer.validated_data
            data.parent_worker_day_id=data.pop('id')
            serializer = WorkerDaySerializer(data)

        serializer.save()

"""
TODO: 

фактический план и такой
подтержденный и нет
подтверждение диапазона дат. 
"""
