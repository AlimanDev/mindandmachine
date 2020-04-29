from django.db.models import OuterRef, Subquery
from django_filters import utils

from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action

from src.base.permissions import FilteredListPermission, EmploymentFilteredListPermission

from src.timetable.serializers import (
    WorkerDaySerializer,
    WorkerDayApproveSerializer,
    WorkerDayWithParentSerializer,
    EmploymentWorkTypeSerializer,
    WorkerConstraintSerializer
)
from src.timetable.filters import WorkerDayFilter, EmploymentWorkTypeFilter, WorkerConstraintFilter
from src.timetable.models import WorkerDay, EmploymentWorkType, WorkerConstraint
from src.timetable.backends import MultiShopsFilterBackend
from src.timetable.worker_day.stat import count_worker_stat

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
            serializer = WorkerDayWithParentSerializer(data=data)
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
            shop_id=serializer.data['shop_id'],
            dt__lte=serializer.data['dt_to'],
            dt__gte=serializer.data['dt_from'],
            is_fact=serializer.data['is_fact'],
            is_approved=False,
        ).select_related('parent_worker_day')

        # Факт
        if serializer.data['is_fact']:
            parent_ids = list(WorkerDay.objects.filter(
                child__in=wdays_to_approve,
                is_fact=serializer.data['is_fact'],
                is_approved=True
            ).values_list('id', flat=True))

            parent_approved_worker_days_subq = WorkerDay.objects.filter(
                child=OuterRef('pk'),
                is_fact=serializer.data['is_fact'],
                is_approved=True
            ).values('parent_worker_day_id')

            wdays_to_approve.update(
                is_approved=True,
                parent_worker_day_id = Subquery(parent_approved_worker_days_subq),
            )
            WorkerDay.objects.filter(id__in=parent_ids).delete()
        # План
        else:
            parent_ids = list(WorkerDay.objects.filter(
                child__in = wdays_to_approve
            ).values_list('id', flat=True))

            WorkerDay.objects.filter(
                parent_worker_day_id__in=wdays_to_approve.values('parent_worker_day_id'),
                is_fact=True
            ).update(
                parent_worker_day_id = Subquery(wdays_to_approve.filter(parent_worker_day_id=OuterRef('parent_worker_day_id')).values('id'))
            )

            wdays_to_approve.update(
                is_approved=True,
                parent_worker_day=None
            )
            WorkerDay.objects.filter(id__in=parent_ids).delete()

        return Response()

    @action(detail=False, methods=['get'], )
    def worker_stat(self, request):
        filterset = self.filter_backends[0]().get_filterset(request, self.get_queryset(), self)
        if filterset.form.is_valid():
            data = filterset.form.cleaned_data
        else:
            raise utils.translate_validation(filterset.errors)

        shop_id = int(request.query_params.get('shop_id'))
        stat = count_worker_stat(shop_id, data)
        return Response(stat)



class EmploymentWorkTypeViewSet(viewsets.ModelViewSet):
    permission_classes = [FilteredListPermission]
    serializer_class = EmploymentWorkTypeSerializer
    filterset_class = EmploymentWorkTypeFilter
    queryset = EmploymentWorkType.objects.all()


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

