import datetime
from itertools import groupby

import pandas as pd
from django.db import transaction
from django.db.models import OuterRef, Subquery, Q, F, Exists
from django.http import HttpResponse
from django.utils import timezone
from django.utils.encoding import escape_uri_path
from django.utils.translation import gettext_lazy as _
from django_filters import utils
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response

from src.base.exceptions import FieldError
from src.base.exceptions import MessageError
from src.base.message import Message
from src.base.models import Employment, Shop, ProductionDay
from src.base.permissions import WdPermission
from src.base.views_abstract import BaseModelViewSet
from src.events.signals import event_signal
from src.timetable.backends import MultiShopsFilterBackend
from src.timetable.events import REQUEST_APPROVE_EVENT_TYPE, APPROVE_EVENT_TYPE
from src.timetable.filters import WorkerDayFilter, WorkerDayStatFilter, VacancyFilter
from src.timetable.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    ShopMonthStat,
    WorkerDayPermission,
    GroupWorkerDayPermission,
)
from src.timetable.serializers import (
    WorkerDaySerializer,
    WorkerDayApproveSerializer,
    WorkerDayWithParentSerializer,
    VacancySerializer,
    DuplicateSrializer,
    DeleteWorkerDaysSerializer,
    ExchangeSerializer,
    UploadTimetableSerializer,
    DownloadSerializer,
    WorkerDayListSerializer,
    DownloadTabelSerializer,
    ChangeRangeListSerializer,
    CopyApprovedSerializer,
    RequestApproveSerializer,
)
from src.timetable.vacancy.utils import cancel_vacancies, confirm_vacancy
from src.timetable.worker_day.stat import count_daily_stat
from src.timetable.worker_day.utils import download_timetable_util, upload_timetable_util, exchange
from src.util.dg.tabel import get_tabel_generator_cls
from src.util.models_converter import Converter
from src.util.openapi.responses import (
    worker_stat_response_schema_dictionary,
    daily_stat_response_schema_dictionary,
    confirm_vacancy_response_schema_dictionary,
    change_range_response_schema_dictionary,
)
from src.util.upload import get_uploaded_file
from .stat import WorkersStatsGetter


class WorkerDayViewSet(BaseModelViewSet):
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
    openapi_tags = ['WorkerDay',]

    def get_queryset(self):
        queryset = WorkerDay.objects.all()

        if self.request.query_params.get('by_code', False):
            return queryset.annotate(
                shop_code=F('shop__code'),
                user_login=F('worker__username'),
            )

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

    def list(self, request, *args, **kwargs):
        if request.query_params.get('hours_details', False):
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
                    if worker_day.work_hours > datetime.timedelta(0):
                        work_seconds = worker_day.work_hours.seconds
                    else:
                        wd_dict['work_hours'] = 0.0
                        data.append(wd_dict)
                        continue
                    work_start = worker_day.dttm_work_start_tabel or worker_day.dttm_work_start
                    work_end = worker_day.dttm_work_end_tabel or worker_day.dttm_work_end
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
    def request_approve(self, request, *args, **kwargs):
        """
        Запрос на подтверждении графика
        """
        serializer = RequestApproveSerializer(data=request.data, **kwargs)
        serializer.is_valid(raise_exception=True)
        event_context = serializer.data.copy()
        transaction.on_commit(lambda: event_signal.send(
            sender=None,
            network_id=request.user.network_id,
            event_code=REQUEST_APPROVE_EVENT_TYPE,
            user_author_id=request.user.id,
            shop_id=serializer.data['shop_id'],
            context=event_context,
        ))
        return Response({})

    @swagger_auto_schema(
        request_body=WorkerDayApproveSerializer,
        responses={200:'empty response'},
        operation_description='''
        Метод для подтверждения графика
        ''',
    )
    @action(detail=False, methods=['post'])
    def approve(self, request):
        kwargs = {'context': self.get_serializer_context()}
        serializer = WorkerDayApproveSerializer(data=request.data, **kwargs)
        serializer.is_valid(raise_exception=True)
        if not serializer.validated_data['wd_types']:
            raise PermissionDenied()

        with transaction.atomic():
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
                # фильтруем только по тем типам, которые переданы
                if wd_type in serializer.validated_data['wd_types']:
                    wd_types_grouped_by_limit.setdefault((limit_days_in_past, limit_days_in_future), []).append(wd_type)
            wd_types_q = Q()
            for (limit_days_in_past, limit_days_in_future), wd_types in wd_types_grouped_by_limit.items():
                q = Q(type__in=wd_types)
                if limit_days_in_past or limit_days_in_future:
                    if limit_days_in_past:
                        q &= Q(dt__gte=today - datetime.timedelta(days=limit_days_in_past))
                    if limit_days_in_future:
                        q &= Q(dt__lte=today + datetime.timedelta(days=limit_days_in_future))
                wd_types_q |= q

            approve_condition = Q(
                wd_types_q,
                Q(shop_id=serializer.data['shop_id']) |
                Q(Q(shop__isnull=True) | Q(type=WorkerDay.TYPE_QUALIFICATION), worker_id__in=user_ids),
                dt__lte=serializer.data['dt_to'],
                dt__gte=serializer.data['dt_from'],
                is_fact=serializer.data['is_fact'],
                is_approved=False,
            )
            wdays_to_approve = WorkerDay.objects.filter(
                approve_condition,
            ).annotate(
                same_approved_exists=Exists(
                    WorkerDay.objects.filter(
                        Q(shop_id=OuterRef('shop_id')) | Q(shop__isnull=True),
                        Q(dttm_work_start=OuterRef('dttm_work_start')) | Q(dttm_work_start__isnull=True),
                        Q(dttm_work_end=OuterRef('dttm_work_end')) | Q(dttm_work_end__isnull=True),
                        Q(work_types=OuterRef('work_types')) | Q(work_types__isnull=True),
                        worker_id=OuterRef('worker_id'),
                        dt=OuterRef('dt'),
                        is_fact=OuterRef('is_fact'),
                        type=OuterRef('type'),
                        is_approved=True,
                    )
                )
            ).filter(same_approved_exists=False)

            worker_dt_pairs_list = list(
                wdays_to_approve.values_list('worker_id', 'dt').order_by('worker_id', 'dt').distinct())
            worker_dates_dict = {}
            for worker_id, dates_grouper in groupby(worker_dt_pairs_list, key=lambda i: i[0]):
                worker_dates_dict[worker_id] = [i[1] for i in list(dates_grouper)]
            if worker_dt_pairs_list:
                worker_days_q = Q()
                for worker_id, dates in worker_dates_dict.items():
                    worker_days_q |= Q(worker_id=worker_id, dt__in=dates)
                WorkerDay.objects_with_excluded.filter(
                    worker_days_q, is_fact=serializer.data['is_fact'],
                ).exclude(
                    id__in=wdays_to_approve.values_list('id', flat=True)
                ).delete()
                list_wd = list(
                    wdays_to_approve.exclude(
                        is_vacancy=True,
                        type='W',
                    ).select_related(
                        'shop',
                        'employment',
                        'employment__position',
                        'employment__position__breaks',
                        'shop__settings__breaks',
                    ).prefetch_related(
                        'worker_day_details',
                    ).distinct()
                )

                wdays_to_approve.update(is_approved=True)

                wds = WorkerDay.objects.bulk_create(
                    [
                        WorkerDay(
                            shop=wd.shop,
                            worker_id=wd.worker_id,
                            employment=wd.employment,
                            dttm_work_start=wd.dttm_work_start,
                            dttm_work_end=wd.dttm_work_end,
                            dt=wd.dt,
                            is_fact=wd.is_fact,
                            is_approved=False,
                            type=wd.type,
                            created_by_id=wd.created_by_id,
                            is_vacancy=wd.is_vacancy,
                            is_outsource=wd.is_outsource,
                            comment=wd.comment,
                            canceled=wd.canceled,
                            need_count_wh=True,
                        )
                        for wd in list_wd
                    ]
                )
                search_wds = {}
                for wd in wds:
                    key_worker = wd.worker_id
                    if not key_worker in search_wds:
                        search_wds[key_worker] = {}
                    search_wds[key_worker][wd.dt] = wd

                WorkerDayCashboxDetails.objects.bulk_create(
                    [
                        WorkerDayCashboxDetails(
                            work_part=details.work_part,
                            worker_day=search_wds[wd.worker_id][wd.dt],
                            work_type_id=details.work_type_id,
                        )
                        for wd in list_wd
                        for details in wd.worker_day_details.all()
                    ]
                )

                # если план, то отмечаем, что график подтвержден
                if not serializer.data['is_fact']:
                    from src.celery.tasks import recalc_wdays

                    ShopMonthStat.objects.filter(
                        shop_id=serializer.data['shop_id'],
                        dt=serializer.validated_data['dt_from'].replace(day=1),
                    ).update(
                        is_approved=True,
                    )

                    if request.user.network.only_fact_hours_that_in_approved_plan:
                        wd_ids = list(WorkerDay.objects.filter(
                            worker_days_q,
                            is_fact=True,
                            type__in=WorkerDay.TYPES_WITH_TM_RANGE,
                        ).values_list('id', flat=True))
                        if wd_ids:
                            transaction.on_commit(lambda wd_ids=wd_ids: recalc_wdays.delay(id__in=wd_ids))

                # TODO: нужно ли как-то разделять события подтверждения факта и плана?
                event_context = serializer.data.copy()
                # TODO: добавлять ли детальную информацию о подтвержденных днях в контекст?
                # event_context['grouped_worker_dates'] = grouped_worker_dates
                transaction.on_commit(lambda: event_signal.send(
                    sender=None,
                    network_id=request.user.network_id,
                    event_code=APPROVE_EVENT_TYPE,
                    user_author_id=request.user.id,
                    shop_id=serializer.data['shop_id'],
                    context=event_context,
                ))

        return Response()

    @swagger_auto_schema(
        operation_description='''
        Возвращает статистику по сотрудникам
        ''',
        responses=worker_stat_response_schema_dictionary,
    )
    @action(detail=False, methods=['get'], filterset_class=WorkerDayStatFilter)
    def worker_stat(self, request):
        filterset = WorkerDayStatFilter(request.query_params)
        if filterset.form.is_valid():
            data = filterset.form.cleaned_data
        else:
            raise utils.translate_validation(filterset.errors)

        stat = WorkersStatsGetter(**data).run()
        return Response(stat)

    @swagger_auto_schema(
        operation_description='''
        Возвращает статистику по дням
        ''',
        responses=daily_stat_response_schema_dictionary,
    )
    @action(detail=False, methods=['get'], filterset_class=WorkerDayStatFilter)
    def daily_stat(self, request):
        filterset = WorkerDayStatFilter(request.query_params)
        if filterset.form.is_valid():
            data = filterset.form.cleaned_data
        else:
            raise utils.translate_validation(filterset.errors)

        stat = count_daily_stat(data)
        return Response(stat)

    @swagger_auto_schema(
        operation_description='''
        Возвращает вакансии
        ''',
    )
    @action(detail=False, methods=['get'], filterset_class=VacancyFilter)
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

    @swagger_auto_schema(
        operation_description='''
        Метод для выхода на вакансию
        ''',
        responses=confirm_vacancy_response_schema_dictionary,
    )
    @action(detail=True, methods=['post'], serializer_class=None)
    def confirm_vacancy(self, request, pk=None):
        result = confirm_vacancy(pk, request.user)

        message = Message(lang=request.user.lang)

        status_code = result['status_code']
        result = message.get_message(result['code'])

        return Response({'result': result}, status=status_code)

    @swagger_auto_schema(
        operation_description='''
        Метод для подтверждения вакансии
        ''',
    )
    @action(detail=True, methods=['post'])
    def approve_vacancy(self, request, pk=None):
        with transaction.atomic():
            vacancy = WorkerDay.objects.filter(pk=pk, is_vacancy=True, is_approved=False).select_for_update().first()
            if vacancy is None:
                raise MessageError(code='no_vacancy_or_approved', lang=request.user.lang)

            if vacancy.worker_id:
                WorkerDay.objects_with_excluded.filter(
                    dt=vacancy.dt,
                    worker_id=vacancy.worker_id,
                    is_fact=vacancy.is_fact,
                    is_approved=True,
                ).exclude(id=vacancy.id).delete()

            vacancy.is_approved = True
            vacancy.save()

        return Response(WorkerDaySerializer(vacancy).data)

    @swagger_auto_schema(
        operation_description='''
        Метод для получения редактируемой версии вакансии
        ''',
    )
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

    @swagger_auto_schema(
        request_body=ChangeRangeListSerializer,
        operation_description='''
        Метод для изменения нескольких дней одновременно
        ''',
        responses=change_range_response_schema_dictionary,
    )
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
                    type=range['type'],
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
                                type=range['type'],
                                created_by=self.request.user,
                            )
                        )
                WorkerDay.objects.bulk_create(wdays_to_create)

                res[range['worker'].tabel_code] = {
                    'deleted_count': deleted[1].get('timetable.WorkerDay', 0),
                    'existing_count': len(existing_dates),
                    'created_count': len(wdays_to_create)
                }

        return Response(res)

    # @action(detail=False, methods=['post'])
    # def change_list(self, request):
    #     data = ListChangeSrializer(data=request.data, context={'request': request})
    #     data.is_valid(raise_exception=True)
    #     data = data.validated_data
    #     is_type_with_tm_range = WorkerDay.is_type_with_tm_range(data['type'])
    #
    #     response = {}
    #
    #     shop_id = data['shop_id']
    #     shop = Shop.objects.get(id=shop_id)
    #
    #     work_type = WorkType.objects.get(id=data['work_type']) if data['work_type'] else None
    #     work_types = {}
    #     employments = {
    #         e.user_id: e
    #         for e in Employment.objects.get_active(
    #             network_id=shop.network_id,
    #             user_id__in=data['workers'].keys(),
    #             shop_id=shop_id,
    #         )
    #     }
    #     for user_id, dates in data['workers'].items():
    #         employment = employments.get(user_id, None)
    #         wds = []
    #         for dt in dates:
    #             wd_args = {
    #                 'type': data['type'],
    #                 'employment': employment,
    #                 'created_by': request.user,
    #                 'comment': data['comment'],
    #                 'dttm_added': timezone.now(),
    #                 'is_vacancy': False,
    #             }
    #             if is_type_with_tm_range:
    #                 dttm_work_start = timezone.datetime.combine(dt, data[
    #                     'tm_work_start'])  # на самом деле с фронта приходят время а не дата-время
    #                 tm_work_end = data['tm_work_end']
    #                 dttm_work_end = timezone.datetime.combine(dt, tm_work_end) if tm_work_end > data['tm_work_start'] else \
    #                     timezone.datetime.combine(dt + timezone.timedelta(days=1), tm_work_end)
    #                 wd_args.update({
    #                     'dttm_work_start': dttm_work_start,
    #                     'dttm_work_end': dttm_work_end,
    #                 })
    #             wd, created = WorkerDay.objects.filter(Q(shop_id=shop_id)|Q(shop__isnull=True)).update_or_create(
    #                 worker_id=user_id,
    #                 dt=dt,
    #                 is_approved=False,
    #                 is_fact=False,
    #                 defaults=wd_args,
    #             )
    #             wd_details = WorkerDayCashboxDetails.objects.filter(worker_day=wd)
    #             work_types.update({
    #                 wd.work_type_id: wd.work_type.shop_id
    #                 for wd in wd_details.select_related('work_type')
    #             })
    #             wd_details.delete()
    #             #TODO add cancel worker day
    #             # if not created and wd_details.exists():
    #             #     old_work_type = wd_details.first().work_type
    #             #     if old_work_type not in work_types:
    #             #         work_types.append(old_work_type)
    #             #     if wd_details.filter(is_vacancy=True).exists():
    #             #         for wd_detail in wd_details.filter(is_vacancy=True):
    #             #             cancel_vacancy(wd_detail.id)
    #             #             worker_day.canceled = True
    #             #     else:
    #             #         worker_day.canceled = False
    #             #     wd_details.filter(is_vacancy=False).delete()
    #             # else:
    #             #     worker_day.canceled = False
    #             if created:
    #                 wd.parent_worker_day = WorkerDay.objects.filter(
    #                     worker_id=user_id,
    #                     dt=dt,
    #                     shop_id=shop_id,
    #                     is_approved=True,
    #                 ).first()
    #                 wd.save()
    #             if wd.type == WorkerDay.TYPE_WORKDAY:
    #                 WorkerDayCashboxDetails.objects.create(
    #                     work_type=work_type,
    #                     worker_day=wd,
    #                 )
    #
    #             wds.append(wd)
    #
    #         response[user_id] = WorkerDaySerializer(wds, many=True).data
    #
    #     if work_type and data['type'] == WorkerDay.TYPE_WORKDAY:
    #         cancel_vacancies(work_type.shop_id, work_type.id)
    #     if len(work_types):
    #         for wt, sh_id in work_types.items():
    #             create_vacancies_and_notify(sh_id, wt)
    #
    #     return Response(response, status=200)

    @swagger_auto_schema(
        request_body=CopyApprovedSerializer,
        operation_description='''
        Метод для копирования подтвержденных рабочих дней в черновик
        ''',
        responses={200:WorkerDaySerializer(many=True)},
    )
    @action(detail=False, methods=['post'])
    def copy_approved(self, request):
        data = CopyApprovedSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data = data.validated_data
        with transaction.atomic():
            fact_filter = {}
            if data['type'] == CopyApprovedSerializer.TYPE_PLAN_TO_FACT:
                fact_filter['type__in'] = list(WorkerDay.TYPES_WITH_TM_RANGE)
                fact_filter['type__in'].append(WorkerDay.TYPE_EMPTY)
            if data['type'] == CopyApprovedSerializer.TYPE_FACT_TO_FACT:
                fact_filter['is_fact'] = True
            else:
                fact_filter['is_fact'] = False
            list_wd = list(
                WorkerDay.objects.exclude(
                    is_vacancy=True,
                ).filter(
                    dt__in=data['dates'],
                    worker_id__in=data['worker_ids'],
                    is_approved=True,
                    **fact_filter,
                ).select_related(
                    'shop', 
                    'employment', 
                    'employment__position', 
                    'employment__position__breaks',
                    'shop__settings__breaks',
                ).prefetch_related(
                    'worker_day_details',
                )
            )
            fact_filter['is_fact'] = True if data['type'] in (CopyApprovedSerializer.TYPE_PLAN_TO_FACT, CopyApprovedSerializer.TYPE_FACT_TO_FACT) else False
            WorkerDay.objects_with_excluded.exclude(
                is_vacancy=True,
            ).filter(
                dt__in=data['dates'],
                worker_id__in=data['worker_ids'],
                is_approved=False,
                **fact_filter,
            ).delete()

            WorkerDay.objects.bulk_create(
                [
                    WorkerDay(
                        shop=wd.shop,
                        worker_id=wd.worker_id,
                        employment=wd.employment,
                        dttm_work_start=wd.dttm_work_start,
                        dttm_work_end=wd.dttm_work_end,
                        dt=wd.dt,
                        is_fact=fact_filter['is_fact'],
                        is_approved=False,
                        type=wd.type,
                        created_by_id=wd.created_by_id,
                        is_vacancy=wd.is_vacancy,
                        is_outsource=wd.is_outsource,
                        comment=wd.comment,
                        canceled=wd.canceled,
                        need_count_wh=True,
                    )
                    for wd in list_wd
                ]
            )
            wds = WorkerDay.objects.exclude(
                is_vacancy=True,
            ).filter(
                dt__in=data['dates'],
                worker_id__in=data['worker_ids'],
                is_approved=False,
                **fact_filter,
            )
            search_wds = {}
            for wd in wds:
                key_worker = wd.worker_id
                if not key_worker in search_wds:
                    search_wds[key_worker] = {}
                search_wds[key_worker][wd.dt] = wd
            
            WorkerDayCashboxDetails.objects.bulk_create(
                [
                    WorkerDayCashboxDetails(
                        work_part=details.work_part,
                        worker_day=search_wds[wd.worker_id][wd.dt],
                        work_type_id=details.work_type_id,
                    )
                    for wd in list_wd
                    for details in wd.worker_day_details.all()
                ]
            )
        
        return Response(WorkerDayListSerializer(wds.prefetch_related('worker_day_details'), many=True, context={'request':request}).data)

    @swagger_auto_schema(
        request_body=DuplicateSrializer,
        operation_description='''
        Метод для копирования рабочих дней
        ''',
        responses={200:WorkerDaySerializer(many=True)},
    )
    @action(detail=False, methods=['post'])
    def duplicate(self, request):
        data = DuplicateSrializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        data = data.validated_data
        to_worker_id = data['to_worker_id']

        with transaction.atomic():
            main_worker_days = list(WorkerDay.objects.filter(
                id__in=data['from_workerday_ids'],
                is_fact=False,
            ).select_related(
                'worker',
                'shop__settings__breaks',
            ).order_by('dt'))
            main_worker_days_details_set = list(WorkerDayCashboxDetails.objects.filter(
                worker_day__in=main_worker_days,
            ).select_related('work_type'))

            main_worker_days_details = {}
            for detail in main_worker_days_details_set:
                key = detail.worker_day_id
                if key not in main_worker_days_details:
                    main_worker_days_details[key] = []
                main_worker_days_details[key].append(detail)

            trainee_worker_days = WorkerDay.objects_with_excluded.filter(
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

                worker_active_empl = Employment.objects.get_active_empl_for_user(
                    network_id=blank_day.worker.network_id, user_id=to_worker_id,
                    dt=dt,
                    priority_shop_id=blank_day.shop_id,
                ).select_related(
                    'position__breaks',
                ).first()

                # не создавать день, если нету активного трудоустройства на эту дату
                if not worker_active_empl:
                    raise ValidationError(
                        'Невозможно создать дни в выбранные даты. '
                        'Пожалуйста, проверьте наличие активного трудоустройства у сотрудника.'
                    )

                new_wd = WorkerDay.objects.create(
                    worker_id=to_worker_id,
                    employment=worker_active_empl,
                    dt=dt,
                    shop=blank_day.shop,
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

    @swagger_auto_schema(
        request_body=DeleteWorkerDaysSerializer,
        operation_description='''
        Метод для удаления рабочих дней
        ''',
        responses={200:'empty response'},
    )
    @action(detail=False, methods=['post'])
    def delete_worker_days(self, request):
        data = DeleteWorkerDaysSerializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        data = data.validated_data
        filt = {}
        if data['exclude_created_by']:
            filt['created_by__isnull'] = True
        WorkerDay.objects_with_excluded.filter(
            is_approved=False,
            is_fact=data['is_fact'], 
            worker_id__in=data['worker_ids'],
            dt__in=data['dates'],
            **filt,
        ).delete()

        return Response()

    @swagger_auto_schema(
        request_body=ExchangeSerializer,
        operation_description='''
        Метод для обмена рабочими сменами в черновике
        ''',
        responses={200:WorkerDaySerializer(many=True)},
    )
    @action(detail=False, methods=['post'])
    def exchange(self, request):
        data = ExchangeSerializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        data = data.validated_data
        data['is_approved'] = False
        data['user'] = request.user
        return Response(WorkerDaySerializer(exchange(data, self.error_messages), many=True).data)

    @swagger_auto_schema(
        request_body=ExchangeSerializer,
        operation_description='''
        Метод для обмена подтвержденными рабочими сменами
        ''',
        responses={200:WorkerDaySerializer(many=True)},
    )
    @action(detail=False, methods=['post'])
    def exchange_approved(self, request):
        data = ExchangeSerializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        data = data.validated_data
        data['is_approved'] = True
        data['user'] = request.user
        return Response(WorkerDaySerializer(exchange(data, self.error_messages), many=True).data)

    @swagger_auto_schema(
        request_body=UploadTimetableSerializer,
        responses={200: 'empty response'},
        operation_description='''
        Загружает плановое расписание в систему.\n
        Должен быть прикреплён файл с расписанием в формате excel в поле file.
        ''',
    )
    @action(detail=False, methods=['post'])
    @get_uploaded_file
    def upload(self, request, file):
        data = UploadTimetableSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data.validated_data['lang'] = request.user.lang
        data.validated_data['network_id'] = request.user.network_id
        return upload_timetable_util(data.validated_data, file)

    @swagger_auto_schema(
        request_body=UploadTimetableSerializer,
        responses={200: 'empty response'},
        operation_description='''
        Загружает фактическое расписание в систему.\n
        Должен быть прикреплён файл с расписанием в формате excel в поле file.
        ''',
    )
    @action(detail=False, methods=['post'])
    @get_uploaded_file
    def upload_fact(self, request, file):
        data = UploadTimetableSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        data.validated_data['lang'] = request.user.lang
        data.validated_data['network_id'] = request.user.network_id
        return upload_timetable_util(data.validated_data, file, is_fact=True)

    @swagger_auto_schema(
        query_serializer=DownloadSerializer,
        responses={200:'Файл с расписанием в формате excel.'},
        operation_description='''
        Метод для скачивания графика работы сотрудников.
        ''',
    )
    @action(detail=False, methods=['get'], filterset_class=None)
    def download_timetable(self, request):
        data = DownloadSerializer(data=request.query_params)
        data.is_valid(raise_exception=True)
        return download_timetable_util(request, data.validated_data)

    @swagger_auto_schema(
        query_serializer=DownloadSerializer,
        responses={200:'Файл с табелем'},
        operation_description='''
        Метод для скачивания табеля для подразделения.
        '''
    )
    @action(detail=False, methods=['get'], filterset_class=None)
    def download_tabel(self, request):
        serializer = DownloadTabelSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        shop = Shop.objects.get(id=serializer.validated_data.get('shop_id'))
        dt_from = serializer.validated_data.get('dt_from')
        dt_to = serializer.validated_data.get('dt_to')
        convert_to = serializer.validated_data.get('convert_to')
        tabel_generator_cls = get_tabel_generator_cls(tabel_format=shop.network.download_tabel_template)
        tabel_generator = tabel_generator_cls(shop, dt_from, dt_to)
        response = HttpResponse(
            tabel_generator.generate(convert_to=shop.network.convert_tabel_to or convert_to),
            content_type='application/octet-stream',
        )
        filename = f'Табель_для_подразделения_{shop.code}_от_{timezone.now().strftime("%Y-%m-%d")}.' \
                   f'{shop.network.convert_tabel_to or convert_to}'
        response['Content-Disposition'] = f'attachment; filename={escape_uri_path(filename)}'
        return response
