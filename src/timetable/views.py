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
    WorkerConstraintSerializer,
    ListChangeSrializer,
    DuplicateSrializer,
    DeleteTimetableSerializer,
    ExchangeSerializer,
)
from src.timetable.filters import WorkerDayFilter, EmploymentWorkTypeFilter, WorkerConstraintFilter
from src.timetable.models import WorkerDay, EmploymentWorkType, WorkerConstraint, WorkerDayCashboxDetails
from src.base.models import Employment, Shop, User
from src.timetable.backends import MultiShopsFilterBackend
from django.db.models import OuterRef, Subquery, Q
from django.utils import timezone
from src.main.timetable.worker_exchange.utils import cancel_vacancies, create_vacancies_and_notify, cancel_vacancy
from src.base.exceptions import MessageError
from src.main.timetable.auto_settings.utils import set_timetable_date_from
from src.main.other.notification.utils import send_notification
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



    @action(detail=False, methods=['post'])
    def change_list(self, request):
        data = ListChangeSrializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)

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
                if created:
                    wd.parent_worker_day = WorkerDay.objects.filter(
                        worker_id=user_id,
                        dt=dt,
                        shop_id=shop_id,
                        is_approved=True,
                    ).first()
                    wd.save()
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


    @action(detail=False, methods=['post'])
    def duplicate(request):
        data = DuplicateSrializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        from_worker_id = data['from_worker_id']
        to_worker_id = data['to_worker_id']
        from_dt = data['from_dt']
        to_dt = data['to_dt']

        main_worker_days = list(WorkerDay.objects.qos_current_version().filter(
            worker_id=from_worker_id,
            dt__gte=from_dt,
            dt__lte=to_dt,
            is_approved=data['is_approved'],
        ))
        main_worker_days_details = WorkerDayCashboxDetails.objects.qos_current_version().filter(
            worker_day__in=main_worker_days,
        )
        # todo: add several details, not last
        main_worker_days_details = {wdds.worker_day_id: wdds for wdds in main_worker_days_details}

        trainee_worker_days = WorkerDay.objects.qos_current_version().filter(
            worker_id=to_worker_id,
            dt__gte=from_dt,
            dt__lte=to_dt,
            is_approved=False,
        )
        WorkerDayCashboxDetails.objects.filter(worker_day__in=trainee_worker_days).delete()
        trainee_worker_days.delete()

        created_wds = []
        wdcds_list_to_create = []
        for blank_day in main_worker_days:
            new_wd = WorkerDay.objects.create(
                worker_id=to_worker_id,
                dt=blank_day.dt,
                shop_id=blank_day.shop_id,
                work_hours=blank_day.work_hours,
                type=blank_day.type,
                dttm_work_start=blank_day.dttm_work_start,
                dttm_work_end=blank_day.dttm_work_end,
                is_approved=False,
            )
            created_wds.append(new_wd)
            new_wdcds = main_worker_days_details.get(blank_day.id)
            if new_wdcds:
                wdcds_list_to_create.append(
                    WorkerDayCashboxDetails(
                        worker_day=new_wd,
                        on_cashbox=new_wdcds.on_cashbox,
                        work_type=new_wdcds.work_type,
                        dttm_from=new_wdcds.dttm_from,
                        dttm_to=new_wdcds.dttm_to
                    )
                )

        WorkerDayCashboxDetails.objects.bulk_create(wdcds_list_to_create)
        return Response(WorkerDaySerializer(created_wds, many=True).data)


    @action(detail=False, methods=['post'])
    def delete_timetable(self, request):
        data = DeleteTimetableSerializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        shop_id = data['shop_id']
        worker_day_filter = {}
        worker_day_cashbox_details_filter = {}
        if data.validated_data.get('delete_all'):
            dt_from = set_timetable_date_from(data['dt_from'].year, data['dt_from'].month)
            if dt_from:
                dt_first = dt_from.replace(day=1)
                dt_to = (dt_first + relativedelta(months=1))
                tts = ShopMonthStat.objects.filter(shop_id=shop_id, dt=dt_first)
                for tt in tts:
                    if (tt.status == ShopMonthStat.PROCESSING) and (not tt.task_id is None):
                        try:
                            requests.post(
                                'http://{}/delete_task'.format(settings.TIMETABLE_IP), data=json.dumps({'id': tt.task_id}).encode('ascii')
                            )
                        except (requests.ConnectionError, requests.ConnectTimeout):
                            pass
                        send_notification('D', tt, sender=request.user)
                tts.update(status=ShopMonthStat.NOT_DONE)
            else:
                dt_from = data['dt_from']
                dt_to = data['dt_to'] if data['dt_to'] else (dt_from.replace(day=1) + relativedelta(months=1))

            employments = Employment.objects.get_active(dt_from, dt_to, shop_id=shop_id, auto_timetable=True)
            workers = User.objects.filter(id__in=employments.values_list('user_id'))
        else:
            dt_from = data['dt_from']
            dt_to = data['dt_to']
            if not len(data['users']):
                employments = Employment.objects.get_active(dt_from, dt_to, shop_id=shop_id)
                workers = User.objects.filter(id__in=employments.values_list('user_id'))
            else:
                workers = User.objects.filter(id__in=data['users'])
        if len(data['types']) and not data['delete_all']:
            worker_day_filter['type__in'] = data['types']
            worker_day_cashbox_details_filter['worker_day__type__in'] = data['types']

        if data['except_created_by']:
            worker_day_filter['created_by__isnull'] = True
            worker_day_cashbox_details_filter['worker_day__created_by__isnull'] = True
        
        WorkerDayCashboxDetails.objects.filter(
            Q(work_type__shop_id=shop_id)|Q(work_type__shop_id__isnull=True),
            worker_day__worker__in=workers,
            worker_day__dt__gte=dt_from,
            worker_day__dt__lt=dt_to,
            worker_day__is_approved=False,
            is_vacancy=False,
            **worker_day_cashbox_details_filter,
        ).delete()

        WorkerDayCashboxDetails.objects.filter(
            worker_day__worker__in=workers,
            worker_day__dt__gte=dt_from,
            worker_day__dt__lt=dt_to,
            worker_day__is_approved=False,
            is_vacancy=True,
            **worker_day_cashbox_details_filter,
        ).update(
            worker_day=None
        )
        WorkerDay.objects.filter(
            Q(shop_id=shop_id)|Q(shop_id__isnull=True),
            worker__in=workers,
            dt__gte=dt_from,
            dt__lt=dt_to,
            is_approved=False,
            **worker_day_filter,
        ).delete()
        if data['delete_all']:
            # cancel vacancy
            # todo: add deleting workerdays
            work_type_ids = [w.id for w in WorkType.objects.filter(shop_id=shop_id)]
            wd_details = WorkerDayCashboxDetails.objects.select_related(
                'worker_day', 
                'worker_day__worker', 
                'worker_day__shop',
            ).filter(
                dttm_from__date__gte=dt_from,
                dttm_from__date__lt=dt_to,
                is_vacancy=True,
                work_type_id__in=work_type_ids,
            )
            ids = list(wd_details.values_list('worker_day_id',flat=True))
            # for worker_day_cashbox_detail in wd_details:
            #     notify_about_canceled_vacancy(worker_day_cashbox_detail)
            wd_details.update(
                worker_day=None,
                dttm_deleted=timezone.now(),
                status=WorkerDayCashboxDetails.TYPE_DELETED,
            )
            
            WorkerDay.objects.filter(id__in=ids).delete()
        return Response()


    @action(detail=False, methods=['post'])
    def exchange(self, request):
        def create_worker_day(wd_parent, wd_swap, is_approved):
            parent_worker_day_id = wd_swap.id if is_approved else wd_parent.parent_worker_day_id
            wd_new = WorkerDay(
                type=wd_swap.type,
                dttm_work_start=wd_swap.dttm_work_start,
                dttm_work_end=wd_swap.dttm_work_end,
                worker_id=wd_parent.worker_id,
                dt=wd_parent.dt,
                parent_worker_day_id=parent_worker_day_id,
                created_by=request.user,
                is_approved=False,
            )
            wd_new.save()

            wd_cashbox_details_new = []
            for wd_cashbox_details_parent in wd_swap.workerdaycashboxdetails_set.all():
                wd_cashbox_details_new.append(WorkerDayCashboxDetails(
                    worker_day_id=wd_new.id,
                    on_cashbox_id=wd_cashbox_details_parent.on_cashbox_id,
                    work_type_id=wd_cashbox_details_parent.work_type_id,
                    status=wd_cashbox_details_parent.status,
                    is_tablet=wd_cashbox_details_parent.is_tablet,
                    dttm_from=wd_cashbox_details_parent.dttm_from,
                    dttm_to=wd_cashbox_details_parent.dttm_to,
                ))
            WorkerDayCashboxDetails.objects.bulk_create(wd_cashbox_details_new)

        data = ExchangeSerializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        days = (data['to_dt'] - data['from_dt']).days + 1

        wd_parent_list = list(WorkerDay.objects.qos_current_version().prefetch_related('child').filter(
            worker_id__in=(data['worker1_id'], data['worker2_id']),
            dt__gte=data['from_dt'],
            dt__lte=data['to_dt'],
            is_approved=data['is_approved'],
        ).order_by('dt'))
        if data['is_approved']:
            id_to_delete = [wd.child.first().id for wd in wd_parent_list]
        else:
            id_to_delete = [wd.id for wd in wd_parent_list]

        if len(wd_parent_list) != days * 2:
            raise MessageError(code="no_timetable", lang=request.user.lang)

        day_pairs = []
        for day_ind in range(days):
            day_pair = [wd_parent_list[day_ind * 2], wd_parent_list[day_ind * 2 + 1]]
            if day_pair[0].dt != day_pair[1].dt:
                raise MessageError(code="worker_days_mismatch", lang=request.user.lang)
            day_pairs.append(day_pair)

        for day_pair in day_pairs:
            create_worker_day(day_pair[0], day_pair[1], data['is_approved'])
            create_worker_day(day_pair[1], day_pair[0], data['is_approved'])

        WorkerDay.objects.filter(id__in=id_to_delete).delete()

        return Response()


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
