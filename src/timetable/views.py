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

from src.timetable.backends import MultiShopsFilterBackend
from django.db.models import OuterRef, Subquery


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
        details = []
        if form['details']:
            details = json.loads(form['details'])

        dt_from = form['dt']
        dt_to = form['dt_to']
        if (not dt_to):
            dt_to = dt_from

        is_type_with_tm_range = WorkerDay.is_type_with_tm_range(form['type'])

        response = []
        old_wds = []

        worker = User.objects.get(id=form['worker_id'])
        shop = request.shop
        employment = Employment.objects.get(
            user=worker,
            shop=shop)


        work_type = WorkType.objects.get(id=form['work_type']) if form['work_type'] else None

        for dt in range(int(dt_from.toordinal()), int(dt_to.toordinal()) + 1, 1):
            dt = date.fromordinal(dt)
            try:
                old_wd = WorkerDay.objects.qos_current_version().get(
                    worker_id=worker.id,
                    dt=dt,
                    shop=shop
                )
                action = 'update'
            except WorkerDay.DoesNotExist:
                old_wd = None
                action = 'create'
            except WorkerDay.MultipleObjectsReturned:
                if (not form['dt_to']):
                    return JsonResponse.multiple_objects_returned()
                response.append({
                    'action': 'MultypleObjectsReturnedError',
                    'dt': dt,
                })
                continue

            if old_wd:
                # Не пересохраняем, если тип не изменился
                if old_wd.type == form['type'] and not is_type_with_tm_range:
                    if (not form['dt_to']):
                        return JsonResponse.success()
                    response.append({
                        'action': 'TypeNotChanged',
                        'dt': dt
                    })
                    continue

            res = {
                'action': action
            }


            wd_args = {
                'dt': dt,
                'type': form['type'],
                'worker_id': worker.id,
                'shop': shop,
                'employment': employment,
                'parent_worker_day': old_wd,
                'created_by': request.user,
                'comment': form['comment'],
            }

            if is_type_with_tm_range:
                dttm_work_start = datetime.combine(dt, form[
                    'tm_work_start'])  # на самом деле с фронта приходят время а не дата-время
                tm_work_end = form['tm_work_end']
                dttm_work_end = datetime.combine(dt, tm_work_end) if tm_work_end > form['tm_work_start'] else \
                    datetime.combine(dt + timedelta(days=1), tm_work_end)
                break_triplets = json.loads(shop.break_triplets)
                work_hours = WorkerDay.count_work_hours(break_triplets, dttm_work_start, dttm_work_end)
                wd_args.update({
                    'dttm_work_start': dttm_work_start,
                    'dttm_work_end': dttm_work_end,
                    'work_hours': work_hours,
                })

            new_worker_day = WorkerDay.objects.create(
                **wd_args
            )
            if new_worker_day.type == WorkerDay.TYPE_WORKDAY:
                if len(details):
                    for item in details:
                        dttm_to = Converter.parse_time(item['dttm_to'])
                        dttm_from = Converter.parse_time(item['dttm_from'])
                        WorkerDayCashboxDetails.objects.create(
                            work_type_id=item['work_type'],
                            worker_day=new_worker_day,
                            dttm_from=datetime.combine(dt, dttm_from),
                            dttm_to=datetime.combine(dt, dttm_to) if dttm_to > dttm_from\
                                else datetime.combine(dt + timedelta(days=1), dttm_to)
                        )

                else:
                    WorkerDayCashboxDetails.objects.create(
                        work_type=work_type,
                        worker_day=new_worker_day,
                        dttm_from=new_worker_day.dttm_work_start,
                        dttm_to=new_worker_day.dttm_work_end
                    )


            res['day'] = WorkerDayConverter.convert(new_worker_day)

            response.append(res)
            if old_wd:
                old_wds.append(old_wd)

        old_cashboxdetails = WorkerDayCashboxDetails.objects.filter(
            worker_day__in=old_wds,
            dttm_deleted__isnull=True
        ).first()

        if work_type and form['type'] == WorkerDay.TYPE_WORKDAY:
            cancel_vacancies(work_type.shop_id, work_type.id)
        if old_cashboxdetails:
            create_vacancies_and_notify(old_cashboxdetails.work_type.shop_id, old_cashboxdetails.work_type_id)

        if (not form['dt_to']):
            response = response[0]

        return JsonResponse.success(response)


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
