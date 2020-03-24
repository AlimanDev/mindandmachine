from rest_framework import viewsets, mixins
from rest_framework.response import Response
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated

from src.base.permissions import FilteredListPermission

from src.timetable.models import WorkerDay, WorkerDayApprove, WorkerWorkType, WorkerConstraint
from src.timetable.serializers import WorkerDaySerializer, WorkerDayApproveSerializer, WorkerWorkTypeSerializer, WorkerConstraintSerializer
from src.timetable.filters import MultiShopsFilterBackend, WorkerDayFilter, WorkerDayApproveFilter, WorkerWorkTypeFilter, WorkerConstraintFilter


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
        worker_day_approve=serializer.save()
        dt_from = worker_day_approve.dt_from
        dt_to = worker_day_approve.dt_to

        WorkerDay.objects.filter(
            dttm_deleted__isnull=True,
            worker_day_approve_id__isnull=True,
            shop_id=worker_day_approve.shop_id,
            dt__lte=dt_to,
            dt__gte=dt_from,
            is_fact=worker_day_approve.is_fact,
        ).update(
            worker_day_approve_id=worker_day_approve.id
        )

        if worker_day_approve.is_fact:
            worker_days = WorkerDay.objects.filter(
                dttm_deleted__isnull=True,
                child__worker_day_approve_id=worker_day_approve.id,
                is_fact=True
            )
            for wd in worker_days:
                parent = wd.parent_worker_day
                wd.child.filter(
                    dttm_deleted__isnull=True
                ).update(parent_worker_day = parent)
                parent.delete()
        else:
            new_plans = WorkerDay.objects.filter(
                dttm_deleted__isnull=True,
                worker_day_approve_id=worker_day_approve.id,
            )
            for new_plan in new_plans:
                parent = new_plan.parent_worker_day
                if parent:
                    parent.child.filter(is_fact=True).update(
                        dttm_deleted__isnull=True,
                        parent_worker_day_id=new_plan.id
                    )
                    parent.delete()


        return worker_day_approve

    def perform_destroy(self, instance):
        WorkerDay.objects.filter(
            dttm_deleted__isnull=True,
            worker_day_approve=instance
        ).update(worker_day_approve=None)
        instance.delete()


class WorkerDayViewSet(viewsets.ModelViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [FilteredListPermission]
    serializer_class = WorkerDaySerializer
    filterset_class = WorkerDayFilter
    queryset = WorkerDay.objects.qos_filter_version(1)
    filter_backends = [MultiShopsFilterBackend]

    # тут переопределяется update потому что надо в Response вернуть
    # не тот объект, который был изначально
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if serializer.instance.worker_day_approve_id:
            data = serializer.validated_data
            data['parent_worker_day_id']=serializer.instance.id
            serializer = WorkerDaySerializer(data=data)
            serializer.is_valid(raise_exception=True)

        serializer.save()

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)


class WorkerWorkTypeViewSet(viewsets.ModelViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [FilteredListPermission]
    serializer_class = WorkerWorkTypeSerializer
    filterset_class = WorkerWorkTypeFilter
    queryset = WorkerWorkType.objects.all()


class WorkerConstraintViewSet(viewsets.ModelViewSet):
    authentication_classes = [SessionAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = WorkerConstraintSerializer
    filterset_class = WorkerConstraintFilter
    queryset = WorkerConstraint.objects.all()
