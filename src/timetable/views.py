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
    WorkerConstraintSerializer,
    ListChangeSrializer,
)
from src.timetable.filters import WorkerDayFilter, EmploymentWorkTypeFilter, WorkerConstraintFilter
from src.timetable.models import WorkerDay, EmploymentWorkType, WorkerConstraint
from src.base.models import Employment, Shop
from src.timetable.backends import MultiShopsFilterBackend
from django.db.models import OuterRef, Subquery
from django.utils import timezone
from src.main.timetable.worker_exchange.utils import cancel_vacancies, create_vacancies_and_notify, cancel_vacancy


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


    @action(detail=False, methods=['post'])
    def change_list(self, request):
        data = ListChangeSrializer(data=request.data)

        is_type_with_tm_range = WorkerDay.is_type_with_tm_range(data['type'])

        response = {}

        shop_id = data['shop_id']
        shop = Shop.objects.get(id=shop_id)

        work_type = WorkType.objects.get(id=data['work_type']) if data['work_type'] else None
        work_types = []
        for user_id, dates in data['workers']:
            employment = Employment.objects.get_active(
                user_id=user_id,
                shop_id=shop_id,
            )
            wds = []
            for dt in dates:
                wd_args = {
                    'type': data['type'],
                    'employment': employment,
                    'created_by': request.user,
                    'comment': data['comment'],
                    'dttm_added': timezone.now(),
                }
                if is_type_with_tm_range:
                    dttm_work_start = datetime.combine(dt, data[
                        'tm_work_start'])  # на самом деле с фронта приходят время а не дата-время
                    tm_work_end = data['tm_work_end']
                    dttm_work_end = datetime.combine(dt, tm_work_end) if tm_work_end > data['tm_work_start'] else \
                        datetime.combine(dt + timedelta(days=1), tm_work_end)
                    break_triplets = json.loads(shop.break_triplets)
                    work_hours = WorkerDay.count_work_hours(break_triplets, dttm_work_start, dttm_work_end)
                    wd_args.update({
                        'dttm_work_start': dttm_work_start,
                        'dttm_work_end': dttm_work_end,
                        'work_hours': work_hours,
                    })
                wd, created = WorkerDay.objects.qos_current_version().update_or_create(
                    worker_id=user_id,
                    dt=dt,
                    shop_id=shop_id,
                    is_approved=False,
                    defaults=wd_args,
                )
                wd_details = WorkerDayCashboxDetails.objects.filter(worker_day=wd)
                if not created and wd_details.exists():
                    old_work_type = wd_details.first().work_type
                    if old_work_type not in work_types:
                        work_types.append(old_work_type)
                    if wd_details.filter(is_vacancy=True).exists():
                        for wd_detail in wd_details.filter(is_vacancy=True):
                            cancel_vacancy(wd_detail.id)
                            # worker_day.canceled = True
                    else:
                        pass
                        # worker_day.canceled = False
                    wd_details.filter(is_vacancy=False).delete()
                else:
                    pass
                    # worker_day.canceled = False
                if wd.type == WorkerDay.TYPE_WORKDAY:      
                    WorkerDayCashboxDetails.objects.create(
                        work_type=work_type,
                        worker_day=wd,
                        dttm_from=wd.dttm_work_start,
                        dttm_to=wd.dttm_work_end
                    )

                wds.append(wd)

            response[user_id] = WorkerDaySerializer(wds, many=True)
                
        if work_type and data['type'] == WorkerDay.TYPE_WORKDAY:
            cancel_vacancies(work_type.shop_id, work_type.id)
        if len(work_types):
            for wt in work_types:
                create_vacancies_and_notify(wt.shop_id, wt.id)

        return Response(response, status=200)


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
