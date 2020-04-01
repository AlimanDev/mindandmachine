from rest_framework import viewsets, mixins
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from src.base.permissions import FilteredListPermission, EmploymentFilteredListPermission

from src.timetable.models import WorkerDay, WorkerWorkType, WorkerConstraint
from src.timetable.serializers import WorkerDaySerializer, WorkerWorkTypeSerializer, WorkerConstraintSerializer, WorkerDayApproveSerializer
from src.timetable.filters import WorkerDayFilter, WorkerWorkTypeFilter, WorkerConstraintFilter
from src.timetable.backends import MultiShopsFilterBackend


class WorkerDayViewSet(viewsets.ModelViewSet):
    permission_classes = [FilteredListPermission]
    serializer_class = WorkerDaySerializer
    filterset_class = WorkerDayFilter
    queryset = WorkerDay.objects.all()
    filter_backends = [MultiShopsFilterBackend]

    # тут переопределяется update а не perform_update потому что надо в Response вернуть
    # не тот объект, который был изначально
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        if instance.is_approved:
            if instance.child.filter(is_fact=instance.is_fact):
                raise ValidationError({"error": "У расписания уже есть неподтвержденная версия."})

            data = serializer.validated_data
            data['parent_worker_day_id']=instance.id
            data['is_fact']=instance.is_fact
            serializer = WorkerDaySerializer(data=data)
            serializer.is_valid(raise_exception=True)

        serializer.save()

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    def perform_destroy(self, worker_day):
        if worker_day.is_approved:
            raise ValidationError({"error": f"Нельзя удалить подтвержденную версию"})
        super().perform_destroy(worker_day)


    @action(detail=False, methods=['post'])
    def approve(self, request):
        kwargs = {'context' : self.get_serializer_context()}
        serializer = WorkerDayApproveSerializer(data=request.data, **kwargs)
        serializer.is_valid(raise_exception=True)


        wdays_to_approve = WorkerDay.objects.filter(
            dttm_deleted__isnull=True,
            shop_id=serializer.data['shop_id'],
            dt__lte=serializer.data['dt_to'],
            dt__gte=serializer.data['dt_from'],
            is_fact=serializer.data['is_fact'],
            is_approved=False,
        )

        if serializer.data['is_fact']:
            worker_days = WorkerDay.objects.filter(
                dttm_deleted__isnull=True,
                child__in=wdays_to_approve,
                is_fact=serializer.data['is_fact']
            )
            for wd in worker_days:
                parent = wd.parent_worker_day
                wd.child.filter(
                    dttm_deleted__isnull=True
                ).update(parent_worker_day = parent,
                         is_approved=True)
                wd.delete()
        else:
            for wd in wdays_to_approve:
                parent = wd.parent_worker_day
                if parent:
                    parent.child.filter(is_fact=True).update(
                        parent_worker_day_id=wd.id
                    )
                    wd.parent_worker_day=None
                    wd.is_approved=True
                    wd.save()
                    parent.delete()

        wdays_to_approve.update(
            is_approved=True
        )

        return Response()



class WorkerWorkTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [FilteredListPermission]
    serializer_class = WorkerWorkTypeSerializer
    filterset_class = WorkerWorkTypeFilter
    queryset = WorkerWorkType.objects.all()


class WorkerConstraintViewSet(viewsets.ModelViewSet):
    permission_classes = [EmploymentFilteredListPermission]
    serializer_class = WorkerConstraintSerializer
    filterset_class = WorkerConstraintFilter
    queryset = WorkerConstraint.objects.all()

    def filter_queryset(self, queryset):
        if self.action == 'list':
            return super().filter_queryset(queryset)
        return queryset

    def get_serializer(self, *args, **kwargs):
        """ if an array is passed, set serializer to many """
        if isinstance(kwargs.get('data', {}), list):
            kwargs['many'] = True
        return super(WorkerConstraintViewSet, self).get_serializer(*args, **kwargs)
