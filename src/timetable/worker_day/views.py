import datetime
import json
from itertools import groupby

import pandas as pd
import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import transaction
from django.db.models import OuterRef, Subquery, Q, F
from django.http import HttpResponse
from django.utils import timezone
from django.utils.encoding import escape_uri_path
from django.utils.translation import gettext_lazy as _
from django_filters import utils
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response

from src.base.exceptions import FieldError
from src.base.exceptions import MessageError
from src.base.message import Message
from src.base.models import Employment, Shop, User, ProductionDay
from src.base.permissions import WdPermission
from src.main.timetable.auto_settings.utils import set_timetable_date_from
from src.timetable.backends import MultiShopsFilterBackend
from src.timetable.filters import WorkerDayFilter, WorkerDayStatFilter, VacancyFilter
from src.timetable.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    WorkType,
    ShopMonthStat,
    WorkerDayPermission,
    GroupWorkerDayPermission,
)
from src.timetable.serializers import (
    WorkerDaySerializer,
    WorkerDayApproveSerializer,
    WorkerDayWithParentSerializer,
    VacancySerializer,
    ListChangeSrializer,
    DuplicateSrializer,
    DeleteTimetableSerializer,
    ExchangeSerializer,
    UploadTimetableSerializer,
    DownloadSerializer,
    WorkerDayListSerializer,
    DownloadTabelSerializer,
    ChangeRangeListSerializer,
)
from src.timetable.vacancy.utils import cancel_vacancies, create_vacancies_and_notify, cancel_vacancy, confirm_vacancy
from src.timetable.worker_day.stat import count_worker_stat, count_daily_stat
from src.timetable.worker_day.utils import download_timetable_util, upload_timetable_util
from src.util.dg.tabel import get_tabel_generator_cls
from src.util.models_converter import Converter
from src.util.upload import get_uploaded_file


class WorkerDayViewSet(viewsets.ModelViewSet):
    error_messages = {
        "worker_days_mismatch": _("Worker days mismatch."),
        "no_timetable": _("Workers don't have timetable."),
        'cannot_delete': _("Cannot_delete approved version."),
        'na_worker_day_exists': _("Not approved version already exists."),
        'no_perm_to_approve_wd_types': _('У вас нет прав на подтверждение типа дня "{wd_type_str}"'),
        'approve_days_interval_restriction': _('У вас нет прав на подтверждения типа дня "{wd_type_str}" '
                                               'в выбранные даты. '
                                               'Необходимо изменить интервал для подтверждения. '
                                               'Разрешенный интевал для подтверждения: {dt_interval}'),
    }

    permission_classes = [WdPermission]  # временно из-за биржи смен vacancy  [FilteredListPermission]
    serializer_class = WorkerDaySerializer
    filterset_class = WorkerDayFilter
    filter_backends = [MultiShopsFilterBackend]

    def get_queryset(self):
        queryset = WorkerDay.objects.all()

        if self.request.query_params.get('by_code', False):
            return queryset.annotate(
                shop_code=F('shop__code'),
                user_login=F('worker__username'),
            )

        if self.action == 'list':
            # временно, пока не решим проблему коллизий дней
            ordered_subq = queryset.filter(
                dt=OuterRef('dt'),
                worker_id=OuterRef('worker_id'),
                is_fact=OuterRef('is_fact'),
                is_approved=OuterRef('is_approved'),
            ).order_by('-is_vacancy', '-id').values_list('id')[:1]
            queryset = queryset.filter(id=Subquery(ordered_subq))

        return queryset

    # тут переопределяется update а не perform_update потому что надо в Response вернуть
    # не тот объект, который был изначально
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        if instance.is_approved:
            if instance.child.filter(is_fact=instance.is_fact):
                raise FieldError(self.error_messages['na_worker_day_exists'])

            data = serializer.validated_data
            data['parent_worker_day_id'] = instance.id
            data['is_fact'] = instance.is_fact
            serializer = WorkerDayWithParentSerializer(data=data)
            serializer.is_valid(raise_exception=True)

        serializer.save()

        if getattr(instance, '_prefetched_objects_cache', None):
            # If 'prefetch_related' has been applied to a queryset, we need to
            # forcibly invalidate the prefetch cache on the instance.
            instance._prefetched_objects_cache = {}

        return Response(serializer.data)

    def perform_destroy(self, worker_day):
        if worker_day.is_vacancy:
            worker_day.is_approved = False
            # worker_day.child.all().delete()
        if worker_day.is_approved:
            raise FieldError(self.error_messages['cannot_delete'])
        super().perform_destroy(worker_day)

    def list(self, request):
        is_tabel = request.query_params.get('is_tabel', False)
        fact_tabel = request.query_params.get('fact_tabel', False)
        if request.query_params.get('hours_details', False) and (is_tabel or fact_tabel):
            data = []
            def _time_to_float(t):
                return t.hour + t.minute / 60 + t.second / 3600
            prod_day_filter = {
                'is_celebration': True,
            }
            if request.query_params.get('dt__gte', False):
                prod_day_filter['dt__gte'] = request.query_params.get('dt__gte', False)
            if request.query_params.get('dt__lte', False):
                prod_day_filter['dt__lte'] = request.query_params.get('dt__lte', False)
            celebration_dates = ProductionDay.objects.filter(**prod_day_filter).values_list('dt', flat=True)

            night_edges = [Converter.parse_time(t) for t in request.user.network.night_edges]
            for worker_day in self.filter_queryset(self.get_queryset().prefetch_related('worker_day_details')):
                wd_dict = WorkerDayListSerializer(worker_day, context=self.get_serializer_context()).data
                if worker_day.type in WorkerDay.TYPES_WITH_TM_RANGE:
                    if is_tabel:
                        work_seconds = worker_day.tabel_work_hours * 3600
                    else:
                        if worker_day.work_hours > datetime.timedelta(0):
                            work_seconds = worker_day.work_hours.seconds
                        else:
                            wd_dict['work_hours'] = 0.0
                            data.append(wd_dict)
                            continue
                    work_start = (worker_day.tabel_dttm_work_start if is_tabel else worker_day.dttm_work_start)
                    work_end = (worker_day.tabel_dttm_work_end if is_tabel else worker_day.dttm_work_end)
                    if not (work_start and work_end):
                        wd_dict['work_hours'] = 0.0
                        data.append(wd_dict)
                        continue

                    wd_dict['work_hours'] = round(work_seconds / 3600, 2)
                    wd_dict['work_hours_details'] = {}
                    if worker_day.dt in celebration_dates:
                        wd_dict['work_hours_details']['H'] = wd_dict['work_hours']
                    else:
                        if work_end.time() <= night_edges[0] and work_start.date() == work_end.date():
                            wd_dict['work_hours_details']['D'] = wd_dict['work_hours']
                            data.append(wd_dict)
                            continue
                        if work_start.time() >= night_edges[0] and work_end.time() <= night_edges[1]:
                            wd_dict['work_hours_details']['N'] = wd_dict['work_hours']
                            data.append(wd_dict)
                            continue

                        if work_start.time() > night_edges[0] or work_start.time() < night_edges[1]:
                            tm_start = _time_to_float(work_start.time())
                        else:
                            tm_start = _time_to_float(night_edges[0])
                        if work_end.time() > night_edges[0] or work_end.time() < night_edges[1]:
                            tm_end = _time_to_float(work_end.time())
                        else:
                            tm_end = _time_to_float(night_edges[1])

                        night_seconds = (tm_end - tm_start if tm_end > tm_start else 24 - (tm_start - tm_end)) * 60 * 60
                        total_seconds = (work_end - work_start).total_seconds()

                        if is_tabel:
                            break_time_seconds = worker_day.tabel_breaktime_seconds or 0
                        else:
                            break_time_seconds = total_seconds - work_seconds

                        wd_dict['work_hours_details']['D'] = round(
                            (total_seconds - night_seconds - break_time_seconds / 2) / 3600, 2)
                        wd_dict['work_hours_details']['N'] = round((night_seconds - break_time_seconds / 2) / 3600, 2)
                        wd_dict['work_hours'] = wd_dict['work_hours_details']['D'] + wd_dict['work_hours_details']['N']
                else:
                    wd_dict['work_hours'] = 0.0
                data.append(wd_dict)
        else:
            data = WorkerDayListSerializer(
                self.filter_queryset(self.get_queryset().prefetch_related('worker_day_details')),
                many=True, context=self.get_serializer_context()
            ).data
        return Response(data)

    @action(detail=False, methods=['post'])
    def approve(self, request):
        kwargs = {'context': self.get_serializer_context()}
        serializer = WorkerDayApproveSerializer(data=request.data, **kwargs)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data['wd_types']:
            raise PermissionDenied()

        wd_perms = GroupWorkerDayPermission.objects.filter(
            group__in=request.user.get_group_ids(
                request.user.network, Shop.objects.get(id=serializer.validated_data['shop_id'])),
            worker_day_permission__action=WorkerDayPermission.APPROVE,
            worker_day_permission__graph_type=WorkerDayPermission.FACT if
                serializer.validated_data['is_fact'] else WorkerDayPermission.PLAN,
        ).select_related('worker_day_permission').values_list(
            'worker_day_permission__wd_type', 'limit_days_in_past', 'limit_days_in_future',
        ).distinct()
        wd_perms_dict = {wdp[0]: wdp for wdp in wd_perms}

        today = (datetime.datetime.now() + datetime.timedelta(hours=3)).date()
        for wd_type in serializer.validated_data.get('wd_types'):
            wdp = wd_perms_dict.get(wd_type)
            wd_type_display_str = dict(WorkerDay.TYPES)[wd_type]
            if wdp is None:
                raise PermissionDenied(
                    self.error_messages['no_perm_to_approve_wd_types'].format(wd_type_str=wd_type_display_str))

            limit_days_in_past = wdp[1]
            limit_days_in_future = wdp[2]
            date_limit_in_past = None
            date_limit_in_future = None
            if limit_days_in_past is not None:
                date_limit_in_past = today - datetime.timedelta(days=limit_days_in_past)
            if limit_days_in_future is not None:
                date_limit_in_future = today + datetime.timedelta(days=limit_days_in_future)
            if date_limit_in_past or date_limit_in_future:
                if (date_limit_in_past and serializer.validated_data.get('dt_from') < date_limit_in_past) or \
                        (date_limit_in_future and serializer.validated_data.get('dt_to') > date_limit_in_future):
                    dt_interval = f'с {Converter.convert_date(date_limit_in_past) or "..."} ' \
                                  f'по {Converter.convert_date(date_limit_in_future) or "..."}'
                    raise PermissionDenied(
                        self.error_messages['approve_days_interval_restriction'].format(
                            wd_type_str=wd_type_display_str,
                            dt_interval=dt_interval,
                        )
                    )

        user_ids = Employment.objects.get_active(
            Shop.objects.get(id=serializer.data['shop_id']).network_id,
            dt_from=serializer.data['dt_from'],
            dt_to=serializer.data['dt_to'],
            shop_id=serializer.data['shop_id'],
        ).values_list('user_id', flat=True)

        wd_types_grouped_by_limit = {}
        for wd_type, limit_days_in_past, limit_days_in_future in wd_perms:
            wd_types_grouped_by_limit.setdefault((limit_days_in_past, limit_days_in_future), []).append(wd_type)
        wd_types_q = Q()
        for (limit_days_in_past, limit_days_in_future), wd_types in wd_types_grouped_by_limit.items():
            q = Q(type__in=wd_types)
            if limit_days_in_past or limit_days_in_future:
                if limit_days_in_past:
                    q &= Q(dt__gte=today - datetime.timedelta(days=limit_days_in_past))
                if limit_days_in_future:
                    q &= Q(dt__lte=today + datetime.timedelta(days=limit_days_in_past))
            wd_types_q |= q

        approve_condition = Q(
            wd_types_q,
            Q(shop_id=serializer.data['shop_id']) | Q(Q(shop__isnull=True) | Q(type=WorkerDay.TYPE_QUALIFICATION), worker_id__in=user_ids),
            dt__lte=serializer.data['dt_to'],
            dt__gte=serializer.data['dt_from'],
            is_fact=serializer.data['is_fact'],
            is_approved=False,
        )

        wdays_to_approve = WorkerDay.objects.get_last_ordered(
            is_fact=serializer.data['is_fact'],
            order_by=[
                'is_approved',
                '-id',
            ]
        ).filter(approve_condition)

        worker_dt_pairs_list = list(
            wdays_to_approve.values_list('worker_id', 'dt').order_by('worker_id', 'dt').distinct())
        if worker_dt_pairs_list:
            worker_days_q = Q()
            for worker_id, dates_grouper in groupby(worker_dt_pairs_list, key=lambda i: i[0]):
                worker_days_q |= Q(worker_id=worker_id, dt__in=[i[1] for i in list(dates_grouper)])
            WorkerDay.objects.filter(
                worker_days_q, is_fact=serializer.data['is_fact'],
            ).exclude(
                id__in=wdays_to_approve.values_list('id', flat=True)
            ).delete()
            wdays_to_approve.update(is_approved=True)

            # если план, то отмечаем, что график подтвержден
            if not serializer.data['is_fact']:
                ShopMonthStat.objects.filter(
                    shop_id=serializer.data['shop_id'],
                    dt=serializer.validated_data['dt_from'].replace(day=1),
                ).update(
                    is_approved=True,
                )
        return Response()

    @action(detail=False, methods=['get'], )
    def worker_stat(self, request):
        filterset = WorkerDayStatFilter(request.query_params)
        if filterset.form.is_valid():
            data = filterset.form.cleaned_data
        else:
            raise utils.translate_validation(filterset.errors)

        stat = count_worker_stat(data)
        return Response(stat)

    @action(detail=False, methods=['get'], )
    def daily_stat(self, request):
        filterset = WorkerDayStatFilter(request.query_params)
        if filterset.form.is_valid():
            data = filterset.form.cleaned_data
        else:
            raise utils.translate_validation(filterset.errors)

        stat = count_daily_stat(data)
        return Response(stat)

    @action(detail=False, methods=['get'], )
    def vacancy(self, request):
        filterset_class = VacancyFilter(request.query_params)
        if not filterset_class.form.is_valid():
            raise utils.translate_validation(filterset_class.errors)
        
        paginator = LimitOffsetPagination()
        queryset = filterset_class.filter_queryset(
            self.get_queryset().filter(is_vacancy=True).select_related('shop', 'worker').prefetch_related('worker_day_details').annotate(
                first_name=F('worker__first_name'),
                last_name=F('worker__last_name'),
                worker_shop=Subquery(Employment.objects.get_active(OuterRef('worker__network_id'),user_id=OuterRef('worker_id')).values('shop_id')[:1]),
            ),
        )
        data = paginator.paginate_queryset(queryset, request)
        data = VacancySerializer(data, many=True, context=self.get_serializer_context())

        return paginator.get_paginated_response(data.data)

    @action(detail=True, methods=['post'])
    def confirm_vacancy(self, request, pk=None):
        result = confirm_vacancy(pk, request.user)

        message = Message(lang=request.user.lang)

        status_code = result['status_code']
        result = message.get_message(result['code'])

        return Response({'result': result}, status=status_code)

    @action(detail=True, methods=['post'])
    def approve_vacancy(self, request, pk=None):
        vacancy = WorkerDay.objects.filter(pk=pk, is_vacancy=True, is_approved=False).first()
        if vacancy is None:
            raise MessageError(code='no_vacancy_or_approved', lang=request.user.lang)
        vacancy.is_approved = True
        vacancy.save()
        if vacancy.worker_id:
            WorkerDay.objects.filter(
                dt=vacancy.dt,
                worker_id=vacancy.worker_id,
                is_fact=vacancy.is_fact,
                is_approved=True,
            ).exclude(id=vacancy.id).delete()
        return Response(WorkerDaySerializer(vacancy).data)

    @action(detail=True, methods=['get'])
    def editable_vacancy(self, request, pk=None):
        vacancy = WorkerDay.objects.filter(pk=pk, is_vacancy=True).first()
        if vacancy is None:
            raise MessageError(code='no_vacancy', lang=request.user.lang)
        if not vacancy.is_approved:
            return Response(WorkerDaySerializer(vacancy).data)
        if vacancy.worker_id:
            raise MessageError(code='cant_edit_vacancy', lang=request.user.lang)
        editable_vacancy = WorkerDay.objects.filter(parent_worker_day=vacancy).first()
        if editable_vacancy is None:
            editable_vacancy = WorkerDay.objects.create(
                shop_id=vacancy.shop_id,
                dt=vacancy.dt,
                dttm_work_start=vacancy.dttm_work_start,
                dttm_work_end=vacancy.dttm_work_end,
                type=vacancy.type,
                is_approved=False,
                created_by=vacancy.created_by,
                comment=vacancy.comment,
                parent_worker_day=vacancy,
                is_vacancy=True,
                is_outsource=vacancy.is_outsource,
            )
            WorkerDayCashboxDetails.objects.bulk_create([
                WorkerDayCashboxDetails(
                    worker_day=editable_vacancy,
                    work_part=d.work_part,
                    work_type_id=d.work_type_id,
                )
                for d in WorkerDayCashboxDetails.objects.filter(worker_day=vacancy)
            ])
        return Response(WorkerDaySerializer(editable_vacancy).data)

    @action(detail=False, methods=['post'])
    def change_range(self, request):
        serializer = ChangeRangeListSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)

        res = {}
        for range in serializer.validated_data['ranges']:
            with transaction.atomic():
                deleted = WorkerDay.objects.filter(
                    worker=range['worker'],
                    dt__gte=range['dt_from'],
                    dt__lte=range['dt_to'],
                    is_approved=range['is_approved'],
                    is_fact=range['is_fact'],
                ).exclude(
                    id__in=Subquery(
                        WorkerDay.objects.filter(
                            dt=OuterRef('dt'),
                            worker=OuterRef('worker'),
                            is_approved=OuterRef('is_approved'),
                            is_fact=OuterRef('is_fact'),
                            type=range['type'],
                        ).order_by('-id').values_list('id')[:1]),
                ).delete()

                existing_dates = list(WorkerDay.objects.filter(
                    worker=range['worker'],
                    dt__gte=range['dt_from'],
                    dt__lte=range['dt_to'],
                    is_approved=range['is_approved'],
                    is_fact=range['is_fact'],
                    type=range['type'],
                ).values_list('dt', flat=True))

                wdays_to_create = []
                for dt in [d.date() for d in pd.date_range(range['dt_from'], range['dt_to'])]:
                    if dt not in existing_dates:
                        wdays_to_create.append(
                            WorkerDay(
                                worker=range['worker'],
                                dt=dt,
                                is_approved=range['is_approved'],
                                is_fact=range['is_fact'],
                                type=range['type']
                            )
                        )
                WorkerDay.objects.bulk_create(wdays_to_create)

                res[range['worker'].tabel_code] = {
                    'deleted_count': deleted[0],
                    'existing_count': len(existing_dates),
                    'created_count': len(wdays_to_create)
                }

        return Response(res)

    @action(detail=False, methods=['post'])
    def change_list(self, request):
        data = ListChangeSrializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        data = data.validated_data
        is_type_with_tm_range = WorkerDay.is_type_with_tm_range(data['type'])

        response = {}

        shop_id = data['shop_id']
        shop = Shop.objects.get(id=shop_id)

        work_type = WorkType.objects.get(id=data['work_type']) if data['work_type'] else None
        work_types = {}
        employments = {
            e.user_id: e
            for e in Employment.objects.get_active(
                network_id=shop.network_id,
                user_id__in=data['workers'].keys(),
                shop_id=shop_id,
            )
        }
        for user_id, dates in data['workers'].items():
            employment = employments.get(user_id, None)
            wds = []
            for dt in dates:
                wd_args = {
                    'type': data['type'],
                    'employment': employment,
                    'created_by': request.user,
                    'comment': data['comment'],
                    'dttm_added': timezone.now(),
                    'is_vacancy': False,
                }
                if is_type_with_tm_range:
                    dttm_work_start = timezone.datetime.combine(dt, data[
                        'tm_work_start'])  # на самом деле с фронта приходят время а не дата-время
                    tm_work_end = data['tm_work_end']
                    dttm_work_end = timezone.datetime.combine(dt, tm_work_end) if tm_work_end > data['tm_work_start'] else \
                        timezone.datetime.combine(dt + timezone.timedelta(days=1), tm_work_end)
                    wd_args.update({
                        'dttm_work_start': dttm_work_start,
                        'dttm_work_end': dttm_work_end,
                    })
                wd, created = WorkerDay.objects.filter(Q(shop_id=shop_id)|Q(shop__isnull=True)).update_or_create(
                    worker_id=user_id,
                    dt=dt,
                    is_approved=False,
                    is_fact=False,
                    defaults=wd_args,
                )
                wd_details = WorkerDayCashboxDetails.objects.filter(worker_day=wd)
                work_types.update({
                    wd.work_type_id: wd.work_type.shop_id
                    for wd in wd_details.select_related('work_type')
                })
                wd_details.delete()
                #TODO add cancel worker day
                # if not created and wd_details.exists():
                #     old_work_type = wd_details.first().work_type
                #     if old_work_type not in work_types:
                #         work_types.append(old_work_type)
                #     if wd_details.filter(is_vacancy=True).exists():
                #         for wd_detail in wd_details.filter(is_vacancy=True):
                #             cancel_vacancy(wd_detail.id)
                #             worker_day.canceled = True
                #     else:
                #         worker_day.canceled = False
                #     wd_details.filter(is_vacancy=False).delete()
                # else:
                #     worker_day.canceled = False
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
                    )

                wds.append(wd)

            response[user_id] = WorkerDaySerializer(wds, many=True).data
                
        if work_type and data['type'] == WorkerDay.TYPE_WORKDAY:
            cancel_vacancies(work_type.shop_id, work_type.id)
        if len(work_types):
            for wt, sh_id in work_types.items():
                create_vacancies_and_notify(sh_id, wt)

        return Response(response, status=200)

    @action(detail=False, methods=['post'])
    def duplicate(self, request):
        data = DuplicateSrializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        data = data.validated_data
        to_worker_id = data['to_worker_id']

        main_worker_days = list(WorkerDay.objects.filter(
            id__in=data['from_workerday_ids'],
            is_fact=False,
        ))
        main_worker_days_details_set = list(WorkerDayCashboxDetails.objects.filter(
            worker_day__in=main_worker_days,
        ).select_related('work_type'))

        main_worker_days_details = {}
        for detail in main_worker_days_details_set:
            key = detail.worker_day_id
            if key not in main_worker_days_details:
                main_worker_days_details[key] = []
            main_worker_days_details[key].append(detail)

        trainee_worker_days = WorkerDay.objects.filter(
            worker_id=to_worker_id,
            dt__in=data['to_dates'],
            is_approved=False,
            is_fact=False,
        )
        trainee_worker_days.delete()

        created_wds = []
        wdcds_list_to_create = []
        length_main_wds = len(main_worker_days)
        for i, dt in enumerate(data['to_dates']):
            i = i % length_main_wds
            blank_day = main_worker_days[i]
            new_wd = WorkerDay.objects.create(
                worker_id=to_worker_id,
                dt=dt,
                shop_id=blank_day.shop_id,
                work_hours=blank_day.work_hours,
                type=blank_day.type,
                dttm_work_start=datetime.datetime.combine(
                    dt, blank_day.dttm_work_start.timetz()) if blank_day.dttm_work_start else None,
                dttm_work_end=datetime.datetime.combine(
                    dt, blank_day.dttm_work_end.timetz()) if blank_day.dttm_work_end else None,
                is_approved=False,
                is_fact=False,
                created_by=request.user,
            )
            created_wds.append(new_wd)
            new_wdcds = main_worker_days_details.get(blank_day.id, [])
            for new_wdcd in new_wdcds:
                wdcds_list_to_create.append(
                    WorkerDayCashboxDetails(
                        worker_day=new_wd,
                        work_type_id=new_wdcd.work_type_id,
                        work_part=new_wdcd.work_part,
                    )
                )

        WorkerDayCashboxDetails.objects.bulk_create(wdcds_list_to_create)

        work_types = [
            (wdcds.work_type.shop_id, wdcds.work_type_id)
            for wdcds in main_worker_days_details_set
        ]

        for shop_id, work_type in set(work_types):
            cancel_vacancies(shop_id, work_type)
        return Response(WorkerDaySerializer(created_wds, many=True).data)

    @action(detail=False, methods=['post'])
    def delete_timetable(self, request):
        data = DeleteTimetableSerializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        data = data.validated_data
        employments = None
        shop_id = data['shop_id']
        shop = Shop.objects.get(id=shop_id)
        worker_day_filter = {
            'is_approved': False,
            'is_fact': False,
        }
        dt_first = data['dt_from'].replace(day=1)
        tts = ShopMonthStat.objects.filter(
            shop_id=shop_id, 
            dt=dt_first,
        )
        processing_tts = tts.filter(status=ShopMonthStat.PROCESSING, task_id__isnull=False)
        for tt in processing_tts:
            try:
                requests.post(
                    'http://{}/delete_task'.format(settings.TIMETABLE_IP), data=json.dumps({'id': tt.task_id}).encode('ascii')
                )
            except (requests.ConnectionError, requests.ConnectTimeout):
                pass
        processing_tts.update(status=ShopMonthStat.NOT_DONE)
        if data.get('delete_all'):
            dt_from = set_timetable_date_from(data['dt_from'].year, data['dt_from'].month)
            if dt_from and not data['dt_to']:
                dt_to = (dt_first + relativedelta(months=1))                
                tts.update(status=ShopMonthStat.NOT_DONE)
            else:
                dt_from = data['dt_from']
                dt_to = data['dt_to'] if data['dt_to'] else (dt_from.replace(day=1) + relativedelta(months=1))

            employments = Employment.objects.get_active(
                shop.network_id,
                dt_from, dt_to, shop_id=shop_id, auto_timetable=True)
            workers = User.objects.filter(id__in=employments.values_list('user_id'))
            employments = list(employments)
        else:
            dt_from = data['dt_from']
            dt_to = data['dt_to']
            if not len(data['users']):
                employments = Employment.objects.get_active(
                    shop.network_id,
                    dt_from, dt_to,
                    shop_id=shop_id,
                    auto_timetable=True)
                workers = User.objects.filter(id__in=employments.values_list('user_id'))
                employments = list(employments)
            else:
                workers = User.objects.filter(id__in=data['users'])
        if len(data['types']) and not data['delete_all']:
            worker_day_filter['type__in'] = data['types']

        if data['except_created_by']:
            worker_day_filter['created_by__isnull'] = True
        

        WorkerDay.objects.filter(
            Q(shop_id=shop_id)|Q(shop_id__isnull=True),
            worker__in=workers,
            dt__gte=dt_from,
            dt__lt=dt_to,
            is_vacancy=False,
            **worker_day_filter,
        ).delete()
        if not employments:
            employments = list(Employment.objects.get_active(
                network_id=shop.network_id,
                dt_from=dt_from,
                dt_to=dt_to,
                shop_id=shop_id,
                user__in=workers))
        WorkerDay.objects.filter(
            employment__in=employments,
            dt__gte=dt_from,
            dt__lt=dt_to,
            is_vacancy=True,
            **worker_day_filter,
        ).delete()
        if data['delete_all']:
            # cancel vacancy
            # todo: add deleting workerdays
            for worker_day in WorkerDay.objects.filter(shop_id=shop_id, is_vacancy=True):
                cancel_vacancy(worker_day.id)
        return Response()

    @action(detail=False, methods=['post'])
    def exchange(self, request):
        new_wds = []
        def create_worker_day(wd_parent, wd_swap, is_approved):
            parent_worker_day_id = wd_swap.id if is_approved else wd_parent.parent_worker_day_id
            wd_new = WorkerDay(
                type=wd_swap.type,
                dttm_work_start=wd_swap.dttm_work_start,
                dttm_work_end=wd_swap.dttm_work_end,
                worker_id=wd_parent.worker_id,
                employment_id=wd_parent.employment_id,
                dt=wd_parent.dt,
                parent_worker_day_id=parent_worker_day_id,
                created_by=request.user,
                is_approved=False,
                is_vacancy=wd_swap.is_vacancy,
            )
            wd_new.save()
            new_wds.append(wd_new)
            WorkerDayCashboxDetails.objects.bulk_create([
                WorkerDayCashboxDetails(
                    worker_day_id=wd_new.id,
                    work_type_id=wd_cashbox_details_parent.work_type_id,
                    work_part=wd_cashbox_details_parent.work_part,
                )
                for wd_cashbox_details_parent in wd_swap.worker_day_details.all()
            ])

        data = ExchangeSerializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        data = data.validated_data
        days = len(data['dates'])

        wd_parent_list = list(WorkerDay.objects.prefetch_related('child').filter(
            worker_id__in=(data['worker1_id'], data['worker2_id']),
            dt__in=data['dates'],
            is_approved=data['is_approved'],
            is_fact=False,
        ).order_by('dt'))
        if data['is_approved']:
            id_to_delete = []
            for wd in wd_parent_list:
                if wd.child.first():
                    id_to_delete.append(wd.child.first().id)
        else:
            id_to_delete = [wd.id for wd in wd_parent_list]

        if len(wd_parent_list) != days * 2:
            raise ValidationError(self.error_messages['no_timetable'])

        day_pairs = []
        for day_ind in range(days):
            day_pair = [wd_parent_list[day_ind * 2], wd_parent_list[day_ind * 2 + 1]]
            if day_pair[0].dt != day_pair[1].dt:
                raise ValidationError(self.error_messages['worker_days_mismatch'])
            day_pairs.append(day_pair)

        for day_pair in day_pairs:
            create_worker_day(day_pair[0], day_pair[1], data['is_approved'])
            create_worker_day(day_pair[1], day_pair[0], data['is_approved'])

        WorkerDay.objects.filter(id__in=id_to_delete).delete()

        return Response(WorkerDaySerializer(new_wds, many=True).data)

    @action(detail=False, methods=['post'])
    @get_uploaded_file
    def upload(self, request, file):
        data = UploadTimetableSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data.validated_data['lang'] = request.user.lang
        data.validated_data['network_id'] = request.user.network_id
        return upload_timetable_util(data.validated_data, file)

    @action(detail=False, methods=['get'])
    def download_timetable(self, request):
        data = DownloadSerializer(data=request.query_params)
        data.is_valid(raise_exception=True)
        return download_timetable_util(request, data.validated_data)

    @action(detail=False, methods=['get'])
    def download_tabel(self, request):
        serializer = DownloadTabelSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        shop = Shop.objects.get(id=serializer.validated_data.get('shop_id'))
        dt_from = serializer.validated_data.get('dt_from')
        dt_to = serializer.validated_data.get('dt_to')
        convert_to = serializer.validated_data.get('convert_to')
        response = HttpResponse(
            get_tabel_generator_cls()(shop, dt_from, dt_to).generate(convert_to=convert_to),
            content_type='application/octet-stream',
        )
        filename = f'Табель_для_подразделения_{shop.code}_от_{timezone.now().strftime("%Y-%m-%d")}.{convert_to}'
        response['Content-Disposition'] = f'attachment; filename={escape_uri_path(filename)}'
        return response
