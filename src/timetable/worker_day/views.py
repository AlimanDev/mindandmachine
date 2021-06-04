import datetime
import io
import json
from itertools import groupby

import pandas as pd
from django.conf import settings
from django.contrib.postgres.aggregates import StringAgg
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import OuterRef, Subquery, Q, F, Exists, Case, When, Value, CharField
from django.db.models.functions import Concat, Cast
from django.http import HttpResponse
from django.utils import timezone
from django.utils.encoding import escape_uri_path
from django.utils.translation import gettext as _
from django_filters import utils
from drf_yasg.utils import swagger_auto_schema
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from src.base.exceptions import FieldError
from src.base.models import Employment, Shop, ProductionDay, Group, User, Employee
from src.base.permissions import WdPermission
from src.base.views_abstract import BaseModelViewSet
from src.events.signals import event_signal
from src.timetable.backends import MultiShopsFilterBackend
from src.timetable.events import REQUEST_APPROVE_EVENT_TYPE, APPROVE_EVENT_TYPE, VACANCY_CONFIRMED_TYPE
from src.timetable.filters import WorkerDayFilter, WorkerDayStatFilter, VacancyFilter
from src.timetable.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    ShopMonthStat,
    WorkerDayPermission,
    GroupWorkerDayPermission,
)
from src.timetable.vacancy.utils import cancel_vacancies, confirm_vacancy
from src.timetable.worker_day.serializers import (
    WorkerDaySerializer,
    WorkerDayApproveSerializer,
    WorkerDayWithParentSerializer,
    VacancySerializer,
    DuplicateSrializer,
    DeleteWorkerDaysSerializer,
    ExchangeSerializer,
    UploadTimetableSerializer,
    GenerateUploadTimetableExampleSerializer,
    DownloadSerializer,
    WorkerDayListSerializer,
    DownloadTabelSerializer,
    ChangeRangeListSerializer,
    CopyApprovedSerializer,
    RequestApproveSerializer,
    CopyRangeSerializer,
    BlockOrUnblockWorkerDayWrapperSerializer,
)
from src.timetable.worker_day.stat import count_daily_stat
from src.timetable.worker_day.tasks import recalc_wdays, recalc_fact_from_records
from src.timetable.worker_day.utils import download_timetable_util, upload_timetable_util, exchange, copy_as_excel_cells
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
        'no_perm_to_approve_wd_types': _('You do not have rights to confirm the day type "{wd_type_str}"'),
        'approve_days_interval_restriction': _('You do not have the rights to confirm the type of day "{wd_type_str}" '
                                               'on the selected dates. '
                                               'You need to change the interval for approve. '
                                               'Allowed inteval for approve: {dt_interval}'),
        'has_no_perm_to_approve_protected_wdays': _('You do not have rights to approve protected worker days ({protected_wdays}). '
                                                   'Please contact your system administrator.'),
        "no_such_user_in_network": _("There is no such user in your network."),
    }

    permission_classes = [WdPermission]  # временно из-за биржи смен vacancy  [FilteredListPermission]
    serializer_class = WorkerDaySerializer
    filterset_class = WorkerDayFilter
    filter_backends = [MultiShopsFilterBackend]
    openapi_tags = ['WorkerDay',]

    def get_queryset(self):
        queryset = WorkerDay.objects.all().prefetch_related('outsources')

        if self.request.query_params.get('by_code', False):
            return queryset.annotate(
                shop_code=F('shop__code'),
                user_login=F('employee__user__username'),
                employment_tabel_code=F('employee__tabel_code'),
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

            for worker_day in self.filter_queryset(self.get_queryset().prefetch_related('worker_day_details').select_related('last_edited_by', 'shop__network')):
                wd_dict = WorkerDayListSerializer(worker_day, context=self.get_serializer_context()).data
                work_hours, work_hours_day, work_hours_night = worker_day.calc_day_and_night_work_hours()
                wd_dict['work_hours'] = work_hours
                wd_dict['work_hours_details'] = {
                    'D': work_hours_day,
                    'N': work_hours_night,
                }
                data.append(wd_dict)
        else:
            data = WorkerDayListSerializer(
                self.filter_queryset(self.get_queryset().prefetch_related('worker_day_details').select_related('last_edited_by')),
                many=True, context=self.get_serializer_context()
            ).data

        if request.query_params.get('fill_empty_days', False):
            employment__tabel_code__in = [
                i for i in request.query_params.get('employment__tabel_code__in', '').split(',') if i]
            employee_id__in = [i for i in request.query_params.get('employee_id__in', '').split(',') if i]
            dt__gte = request.query_params.get('dt__gte')
            dt__lte = request.query_params.get('dt__lte')
            if (employment__tabel_code__in or employee_id__in) and dt__gte and dt__lte:
                response_wdays_dict = {f"{d['employee_id']}_{d['dt']}": d for d in data}

                employees = Employee.objects
                if employee_id__in:
                    employees = employees.filter(id__in=employee_id__in)
                elif employment__tabel_code__in:
                    employees = employees.filter(tabel_code__in=employment__tabel_code__in)

                plan_wdays_dict = {f'{wd.employee_id}_{wd.dt}': wd for wd in WorkerDay.objects.filter(
                    employee__in=employees,
                    dt__gte=dt__gte,
                    dt__lte=dt__lte,
                    is_approved=True,
                    is_fact=False,
                ).exclude(
                    type=WorkerDay.TYPE_EMPTY,
                ).select_related(
                    'employee__user',
                    'shop',
                )}
                for employee in employees:
                    for dt in pd.date_range(dt__gte, dt__lte).date:
                        empl_dt_key = f"{employee.id}_{dt}"
                        resp_wd = response_wdays_dict.get(empl_dt_key)
                        if resp_wd:  # если есть ответ для сотрудника на конкретный день, то пропускаем
                            continue

                        plan_wd = plan_wdays_dict.get(empl_dt_key)

                        # Если нет ни плана ни факта, то добавляем выходной
                        if not plan_wd:
                            d = {
                                "id": None,
                                "worker_id": employee.user_id,
                                "employee_id": employee.id,
                                "shop_id": None,
                                "employment_id": None,  # нужен?
                                "type": "H",
                                "dt": Converter.convert_date(dt),
                                "dttm_work_start": None,
                                "dttm_work_end": None,
                                "dttm_work_start_tabel": None,
                                "dttm_work_end_tabel": None,
                                "comment": None,
                                "is_approved": None,
                                "worker_day_details": [],
                                "outsources": [],
                                "is_fact": None,
                                "work_hours": 0,
                                "parent_worker_day_id": None,
                                "created_by_id": None,
                                "last_edited_by": None,
                                "dttm_modified": None,
                                "is_blocked": None
                            }
                            if self.request.query_params.get('by_code', False):
                                d['shop_code'] = None
                                d['user_login'] = employee.user.username
                                d['employment_tabel_code'] = employee.tabel_code
                            data.append(d)
                            continue

                        dt_now = timezone.now().date()
                        if plan_wd and plan_wd.type in WorkerDay.TYPES_WITH_TM_RANGE:
                            day_in_past = dt < dt_now
                            d = {
                                "id": None,
                                "worker_id": employee.user_id,
                                "employee_id": employee.id,
                                "shop_id": plan_wd.shop_id,
                                "employment_id": plan_wd.employment_id,
                                "type": WorkerDay.TYPE_ABSENSE if day_in_past else WorkerDay.TYPE_WORKDAY,
                                "dt": Converter.convert_date(dt),
                                "dttm_work_start": None,
                                "dttm_work_end": None,
                                "dttm_work_start_tabel": None,
                                "dttm_work_end_tabel": None,
                                "comment": None,
                                "is_approved": None,
                                "worker_day_details": None,
                                "outsources": None,
                                "is_fact": None,
                                "work_hours": 0,
                                "parent_worker_day_id": None,
                                "created_by_id": None,
                                "last_edited_by": None,
                                "dttm_modified": None,
                                "is_blocked": None,
                            }
                            if not day_in_past:
                                d["work_hours_details"] = {
                                  "D": 0
                                }
                            if self.request.query_params.get('by_code', False):
                                d['shop_code'] = plan_wd.shop.code
                                d['user_login'] = employee.user.username
                                d['employment_tabel_code'] = employee.tabel_code
                            data.append(d)

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
                group__in=request.user.get_group_ids(Shop.objects.get(id=serializer.validated_data['shop_id'])),
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
            employee_filter = {}
            if serializer.data.get('employee_ids'):
                employee_filter['employee_id__in'] = serializer.data['employee_ids']
            employee_ids = Employment.objects.get_active(
                Shop.objects.get(id=serializer.data['shop_id']).network_id,
                dt_from=serializer.data['dt_from'],
                dt_to=serializer.data['dt_to'],
                shop_id=serializer.data['shop_id'],
                **employee_filter,
            ).values_list('employee_id', flat=True)

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
                Q(Q(shop__isnull=True) | Q(type=WorkerDay.TYPE_QUALIFICATION), employee_id__in=employee_ids),
                dt__lte=serializer.data['dt_to'],
                dt__gte=serializer.data['dt_from'],
                is_fact=serializer.data['is_fact'],
                is_approved=False,
                **employee_filter,
            )

            wdays_to_approve = WorkerDay.objects.filter(
                approve_condition,
            ).annotate(
                same_approved_exists=Exists(
                    WorkerDay.objects.filter(
                        Q(shop_id=OuterRef('shop_id')) | Q(shop__isnull=True),
                        Q(dttm_work_start=OuterRef('dttm_work_start')),
                        Q(dttm_work_end=OuterRef('dttm_work_end')),
                        Q(work_types=OuterRef('work_types')) | Q(work_types__isnull=True),
                        employee_id=OuterRef('employee_id'),
                        dt=OuterRef('dt'),
                        is_fact=OuterRef('is_fact'),
                        type=OuterRef('type'),
                        is_approved=True,
                    ),
                ),
            ).filter(same_approved_exists=False)

            employee_dt_pairs_list = list(
                wdays_to_approve.values_list('employee_id', 'dt').order_by('employee_id', 'dt').distinct())
            worker_dates_dict = {}
            for employee_id, dates_grouper in groupby(employee_dt_pairs_list, key=lambda i: i[0]):
                worker_dates_dict[employee_id] = [i[1] for i in list(dates_grouper)]
            if employee_dt_pairs_list:
                employee_days_q = Q()
                for employee_id, dates in worker_dates_dict.items():
                    employee_days_q |= Q(employee_id=employee_id, dt__in=dates)

                # если у пользователя нет группы с наличием прав на изменение защищенных дней, то проверяем,
                # что в списке подтверждаемых дней нету защищенных дней, если есть, то выдаем ошибку
                has_permission_to_change_protected_wdays = Group.objects.filter(
                    id__in=request.user.get_group_ids(Shop.objects.get(id=serializer.validated_data['shop_id'])),
                    has_perm_to_change_protected_wdays=True,
                ).exists()
                if not has_permission_to_change_protected_wdays:
                    protected_wdays = list(WorkerDay.objects.filter(
                        employee_days_q, is_fact=serializer.data['is_fact'],
                        is_blocked=True,
                    ).exclude(
                        id__in=wdays_to_approve.values_list('id', flat=True),
                    ).annotate(
                        employee_user_fio=Concat(
                            F('employee__user__last_name'), Value(' '),
                            F('employee__user__first_name'), Value(' ('),
                            F('employee__user__username'), Value(')'),
                        ),
                    ).values(
                        'employee_user_fio',
                    ).annotate(
                        dates=StringAgg(Cast('dt', CharField()), delimiter=','),
                    ))
                    if protected_wdays:
                        raise PermissionDenied(self.error_messages['has_no_perm_to_approve_protected_wdays'].format(
                            protected_wdays=', '.join(f'{d["employee_user_fio"]}: {d["dates"]}' for d in protected_wdays),
                        ))

                if not serializer.data['is_fact'] and settings.SEND_DOCTORS_MIS_SCHEDULE_ON_CHANGE:
                    from src.celery.tasks import send_doctors_schedule_to_mis
                    mis_data_qs = wdays_to_approve.annotate(
                        approved_wd_type=Subquery(WorkerDay.objects.filter(
                            dt=OuterRef('dt'),
                            employee_id=OuterRef('employee_id'),
                            is_fact=serializer.data['is_fact'],
                            is_approved=True,
                        ).values('type')[:1]),
                        approved_wd_has_doctor_work_type=Exists(WorkerDayCashboxDetails.objects.filter(
                            worker_day__dt=OuterRef('dt'),
                            worker_day__employee_id=OuterRef('employee_id'),
                            worker_day__is_fact=serializer.data['is_fact'],
                            worker_day__is_approved=True,
                            work_type__work_type_name__code='doctor',
                        )),
                        approved_wd_dttm_work_start=Subquery(WorkerDay.objects.filter(
                            dt=OuterRef('dt'),
                            employee_id=OuterRef('employee_id'),
                            is_fact=serializer.data['is_fact'],
                            is_approved=True,
                        ).values('dttm_work_start')[:1]),
                        approved_wd_dttm_work_end=Subquery(WorkerDay.objects.filter(
                            dt=OuterRef('dt'),
                            employee_id=OuterRef('employee_id'),
                            is_fact=serializer.data['is_fact'],
                            is_approved=True,
                        ).values('dttm_work_end')[:1]),
                    ).filter(
                        Q(type=WorkerDay.TYPE_WORKDAY) | Q(approved_wd_type=WorkerDay.TYPE_WORKDAY),
                    ).annotate(
                        action=Case(
                            When(
                                Q(
                                    Q(approved_wd_type__isnull=True) | ~Q(approved_wd_type=WorkerDay.TYPE_WORKDAY),
                                    type=WorkerDay.TYPE_WORKDAY,
                                    work_types__work_type_name__code='doctor',
                                ),
                                then=Value('create', output_field=CharField())
                            ),
                            When(
                                Q(
                                    ~Q(type=WorkerDay.TYPE_WORKDAY),
                                    approved_wd_type=WorkerDay.TYPE_WORKDAY,
                                    approved_wd_has_doctor_work_type=True,
                                ),
                                then=Value('delete', output_field=CharField()),
                            ),
                            When(
                                type=F('approved_wd_type'),
                                work_types__work_type_name__code='doctor',
                                approved_wd_has_doctor_work_type=True,
                                then=Value('update', output_field=CharField()),
                            ),
                            When(
                                type=F('approved_wd_type'),
                                work_types__work_type_name__code='doctor',
                                approved_wd_has_doctor_work_type=False,
                                then=Value('create', output_field=CharField()),
                            ),
                            When(
                                Q(
                                    ~Q(work_types__work_type_name__code='doctor'),
                                    type=F('approved_wd_type'),
                                    approved_wd_has_doctor_work_type=True,
                                ),
                                then=Value('delete', output_field=CharField()),
                            ),
                            default=None, output_field=CharField()
                        ),
                    ).filter(
                        action__isnull=False,
                    ).values(
                        'dt',
                        'employee__user__username',
                        'action',
                        'shop__code',
                        'dttm_work_start',
                        'dttm_work_end',
                        'approved_wd_dttm_work_start',
                        'approved_wd_dttm_work_end',
                    )

                    mis_data = []
                    for d in list(mis_data_qs):
                        if d['action'] == 'delete':
                            d['dttm_work_start'] = d['approved_wd_dttm_work_start']
                            d['dttm_work_end'] = d['approved_wd_dttm_work_end']
                        d.pop('approved_wd_dttm_work_start')
                        d.pop('approved_wd_dttm_work_end')
                        mis_data.append(d)

                    if mis_data:
                        json_data = json.dumps(mis_data, cls=DjangoJSONEncoder)
                        transaction.on_commit(
                            lambda f_json_data=json_data: send_doctors_schedule_to_mis.delay(json_data=f_json_data))

                WorkerDay.objects_with_excluded.filter(
                    employee_days_q, is_fact=serializer.data['is_fact'],
                ).exclude(
                    id__in=wdays_to_approve.values_list('id', flat=True)
                ).exclude(
                    employee_id__isnull=True,
                ).delete()
                list_wd = list(
                    wdays_to_approve.select_related(
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
                            employee_id=wd.employee_id,
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
                            is_blocked=wd.is_blocked,
                        )
                        for wd in list_wd if wd.employee_id  # не копируем день без сотрудника (вакансию) в неподтв. версию
                    ]
                )
                search_wds = {}
                for wd in wds:
                    key_employee = wd.employee_id
                    if not key_employee in search_wds:
                        search_wds[key_employee] = {}
                    search_wds[key_employee][wd.dt] = wd

                WorkerDayCashboxDetails.objects.bulk_create(
                    [
                        WorkerDayCashboxDetails(
                            work_part=details.work_part,
                            worker_day=search_wds[wd.employee_id][wd.dt],
                            work_type_id=details.work_type_id,
                        )
                        for wd in list_wd if wd.employee_id  # TODO: написать тест
                        for details in wd.worker_day_details.all()
                    ]
                )

                # если план, то отмечаем, что график подтвержден
                if not serializer.data['is_fact']:

                    ShopMonthStat.objects.filter(
                        shop_id=serializer.data['shop_id'],
                        dt=serializer.validated_data['dt_from'].replace(day=1),
                    ).update(
                        is_approved=True,
                    )

                    if request.user.network.only_fact_hours_that_in_approved_plan:
                        wd_ids = list(WorkerDay.objects.filter(
                            employee_days_q,
                            is_fact=True,
                            type__in=WorkerDay.TYPES_WITH_TM_RANGE,
                        ).values_list('id', flat=True))
                        if wd_ids:
                            transaction.on_commit(lambda wd_ids=wd_ids: recalc_wdays.delay(id__in=wd_ids))
                    if settings.ZKTECO_INTEGRATION: # если используем терминалы
                            transaction.on_commit(
                                lambda: recalc_fact_from_records.delay(
                                    serializer.validated_data['dt_from'], 
                                    serializer.validated_data['dt_to'], 
                                    shop_ids=[serializer.data['shop_id']]
                                )
                            )

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

                WorkerDay.check_work_time_overlap(
                    employee_days_q=employee_days_q,
                    exc_cls=ValidationError,
                )
                WorkerDay.check_tasks_violations(
                    employee_days_q=employee_days_q,
                    is_approved=True,
                    is_fact=serializer.data['is_fact'],
                    exc_cls=ValidationError,
                )

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
        filterset_class = VacancyFilter(request.query_params, request=request)
        if not filterset_class.form.is_valid():
            raise utils.translate_validation(filterset_class.errors)
        
        paginator = LimitOffsetPagination()
        worker_day_outsource_network_subq = WorkerDay.objects.filter(
            pk=OuterRef('pk'),
            outsources__id=self.request.user.network_id,
        )
        queryset = filterset_class.filter_queryset(
            self.get_queryset().filter(
                is_vacancy=True,
            ).annotate(
                worker_day_outsource_network_exitst=Exists(worker_day_outsource_network_subq),
            ).filter(
                Q(shop__network_id=request.user.network_id) | 
                Q(is_outsource=True, worker_day_outsource_network_exitst=True, is_approved=True), # аутсорс фильтр
            ).select_related(
                'shop',
                'employee__user',
            ).prefetch_related(
                'worker_day_details',
                'outsources',
            ).annotate(
                first_name=F('employee__user__first_name'),
                last_name=F('employee__user__last_name'),
                worker_shop=Subquery(
                    Employment.objects.get_active(
                        OuterRef('employee__user__network_id'),
                        employee_id=OuterRef('employee_id')
                    ).values('shop_id')[:1]
                ),
                user_network_id=F('employee__user__network_id'),
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
        result = confirm_vacancy(pk, request.user, employee_id=self.request.data.get('employee_id', None))
        status_code = result['status_code']
        result = result['text']
        if status_code == 200:
            vacancy = WorkerDay.objects.get(pk=pk)
            work_type = vacancy.work_types.first()
            event_signal.send(
                sender=None,
                network_id=vacancy.shop.network_id,
                event_code=VACANCY_CONFIRMED_TYPE,
                user_author_id=None,
                shop_id=vacancy.shop_id,
                context={
                    'user': {
                        'last_name': request.user.last_name,
                        'first_name': request.user.first_name,
                    },
                    'dt': str(vacancy.dt),
                    'work_type': work_type.work_type_name.name if work_type else 'Без типа работ',
                    'shop_id': vacancy.shop_id,
                },
            )

        return Response({'result': result}, status=status_code)

    @swagger_auto_schema(
        operation_description='''
        Метод для вывывода на вакансию сотрудника
        ''',
        responses=confirm_vacancy_response_schema_dictionary,
    )
    @action(detail=True, methods=['post'], serializer_class=None)
    def confirm_vacancy_to_worker(self, request, pk=None):
        user = User.objects.filter(id=request.data.get('user_id'), network_id=request.user.network_id).first()
        if not user:
            raise ValidationError(self.error_messages["no_such_user_in_network"])
        result = confirm_vacancy(pk, user, employee_id=request.data.get('employee_id', None))
        status_code = result['status_code']
        result = result['text']

        return Response({'result': result}, status=status_code)

    @swagger_auto_schema(
        operation_description='''
        Метод для переназначения сотрудника на вакансию
        ''',
        responses=confirm_vacancy_response_schema_dictionary,
    )
    @action(detail=True, methods=['post'], serializer_class=None)
    def reconfirm_vacancy_to_worker(self, request, pk=None):
        user = User.objects.filter(id=request.data.get('user_id'), network_id=request.user.network_id).first()
        if not user:
            raise ValidationError(self.error_messages["no_such_user_in_network"])
        result = confirm_vacancy(pk, user, employee_id=request.data.get('employee_id', None), reconfirm=True)
        status_code = result['status_code']
        result = result['text']

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
                raise ValidationError(_('This vacancy does not exist or has already been approved.'))

            if vacancy.shop.network_id != request.user.network_id:
                raise ValidationError(_('You can not approve vacancy from other network.'))

            if vacancy.employee_id:
                WorkerDay.objects_with_excluded.filter(
                    dt=vacancy.dt,
                    employee_id=vacancy.employee_id,
                    is_fact=vacancy.is_fact,
                    is_approved=True,
                ).exclude(id=vacancy.id).delete()
                vacancy.is_approved = True
                vacancy.save()

                vacancy_details = WorkerDayCashboxDetails.objects.filter(
                    worker_day=vacancy).values('work_type_id', 'work_part')

                vacancy.id = None
                vacancy.is_approved = False
                vacancy.save()

                WorkerDayCashboxDetails.objects.bulk_create(
                    WorkerDayCashboxDetails(
                        worker_day=vacancy,
                        work_type_id=details['work_type_id'],
                        work_part=details['work_part'],
                    ) for details in vacancy_details
                )
            else:
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
            raise ValidationError(_('There is no such vacancy.'))
        if not vacancy.is_approved:
            return Response(WorkerDaySerializer(vacancy).data)
        if vacancy.empoyee_id:
            raise ValidationError(_('The vacancy cannot be edited because it has already been responded.'))
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
        Метод для создания/обновления дней за период
        Обычно используется для получения отпусков/больничных из 1С ЗУП
        ''',
        responses=change_range_response_schema_dictionary,
    )
    @action(detail=False, methods=['post'])
    def change_range(self, request):
        serializer = ChangeRangeListSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)

        res = {}
        for range in serializer.validated_data['ranges']:
            tabel_code = range['worker']

            with transaction.atomic():
                deleted = WorkerDay.objects.filter(
                    employee__tabel_code=tabel_code,
                    dt__gte=range['dt_from'],
                    dt__lte=range['dt_to'],
                    is_approved=range['is_approved'],
                    is_fact=range['is_fact'],
                ).exclude(
                    type=range['type'],
                ).delete()

                existing_dates = list(WorkerDay.objects.filter(
                    employee__tabel_code=tabel_code,
                    dt__gte=range['dt_from'],
                    dt__lte=range['dt_to'],
                    is_approved=range['is_approved'],
                    is_fact=range['is_fact'],
                    type=range['type'],
                ).values_list('dt', flat=True))

                wdays_to_create = []
                for dt in [d.date() for d in pd.date_range(range['dt_from'], range['dt_to'])]:
                    if dt not in existing_dates:
                        employment = Employment.objects.get_active_empl_by_priority(
                            network_id=self.request.user.network_id,
                            dt=dt,
                            employee__tabel_code=tabel_code,
                        ).first()
                        if employment:
                            wdays_to_create.append(
                                WorkerDay(
                                    employment=employment,
                                    employee_id=employment.employee_id,
                                    dt=dt,
                                    is_approved=range['is_approved'],
                                    is_fact=range['is_fact'],
                                    type=range['type'],
                                    created_by=self.request.user,
                                )
                            )
                WorkerDay.objects.bulk_create(wdays_to_create)

                res[tabel_code] = {
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
                WorkerDay.objects.filter(
                    dt__in=data['dates'],
                    employee_id__in=data['employee_ids'],
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
            WorkerDay.objects_with_excluded.filter(
                dt__in=data['dates'],
                employee_id__in=data['employee_ids'],
                is_approved=False,
                **fact_filter,
            ).delete()

            if data['type'] == CopyApprovedSerializer.TYPE_PLAN_TO_FACT and request.user.network.copy_plan_to_fact_crossing:
                grouped_wds = {}
                for wd in list_wd:
                    grouped_wds.setdefault(wd.employee_id, {})[wd.dt] = wd
                wds_approved =  WorkerDay.objects_with_excluded.filter(
                    dt__in=data['dates'],
                    employee_id__in=data['employee_ids'],
                    is_approved=True,
                    is_fact=True,
                )
                for wd in wds_approved:
                    grouped_wds.setdefault(wd.employee_id, {})[wd.dt] = WorkerDay(
                        shop=wd.shop,
                        employee_id=wd.employee_id,
                        employment=wd.employment,
                        dttm_work_start=wd.dttm_work_start,
                        dttm_work_end=wd.dttm_work_end,
                        dt=wd.dt,
                        is_fact=wd.is_fact,
                        is_approved=wd.is_approved,
                        type=wd.type,
                        created_by_id=wd.created_by_id,
                        is_vacancy=wd.is_vacancy,
                        is_outsource=wd.is_outsource,
                        comment=wd.comment,
                        canceled=wd.canceled,
                        need_count_wh=True,
                    )
                list_wd = [wd for user_data in grouped_wds.values() for wd in user_data.values()]

            WorkerDay.objects.bulk_create(
                [
                    WorkerDay(
                        shop=wd.shop,
                        employee_id=wd.employee_id,
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
            wds = WorkerDay.objects.filter(
                dt__in=data['dates'],
                employee_id__in=data['employee_ids'],
                is_approved=False,
                **fact_filter,
            )
            search_wds = {}
            for wd in wds:
                key_employee = wd.employee_id
                if not key_employee in search_wds:
                    search_wds[key_employee] = {}
                search_wds[key_employee][wd.dt] = wd
            
            WorkerDayCashboxDetails.objects.bulk_create(
                [
                    WorkerDayCashboxDetails(
                        work_part=details.work_part,
                        worker_day=search_wds[wd.employee_id][wd.dt],
                        work_type_id=details.work_type_id,
                    )
                    for wd in list_wd
                    for details in wd.worker_day_details.all()
                ]
            )

            WorkerDay.check_work_time_overlap(
                employee_id__in=data['employee_ids'], dt__in=data['dates'], exc_cls=ValidationError)
        
        return Response(WorkerDayListSerializer(wds.prefetch_related('worker_day_details').select_related('last_edited_by'), many=True, context={'request':request}).data)

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
        to_employee_id = data['to_employee_id']

        with transaction.atomic():
            main_worker_days = list(WorkerDay.objects.filter(
                id__in=data['from_workerday_ids'],
                is_fact=False,
            ).select_related(
                'employee__user',
                'shop__settings__breaks',
            ).order_by('dt'))
            created_wds, work_types = copy_as_excel_cells(
                main_worker_days,
                to_employee_id,
                data['to_dates'],
                created_by=request.user.id
            )
            for shop_id, work_type in set(work_types):
                cancel_vacancies(shop_id, work_type)

            WorkerDay.check_work_time_overlap(
                employee_id=to_employee_id, dt__in=data['to_dates'], exc_cls=ValidationError)

        return Response(WorkerDaySerializer(created_wds, many=True).data)

    @swagger_auto_schema(
        request_body=CopyRangeSerializer,
        operation_description='''
        Метод для копирования рабочих дней
        ''',
        responses={200:WorkerDaySerializer(many=True)},
    )
    @action(detail=False, methods=['post'])
    def copy_range(self, request):
        data = CopyRangeSerializer(data=request.data, context={'request': request})
        data.is_valid(raise_exception=True)
        data = data.validated_data
        from_dates = [
            data['from_copy_dt_from'] + datetime.timedelta(i)
            for i in range((data['from_copy_dt_to'] - data['from_copy_dt_from']).days + 1)
        ]
        to_dates = [
            data['to_copy_dt_from'] + datetime.timedelta(i)
            for i in range((data['to_copy_dt_to'] - data['to_copy_dt_from']).days + 1)
        ]
        employee_ids = data.get('employee_ids')
        created_wds = []
        work_types = []
        with transaction.atomic():
            for employee_id in employee_ids:
                main_worker_days = list(WorkerDay.objects.filter(
                    employee_id=employee_id,
                    dt__in=from_dates,
                    is_fact=False,
                    is_approved=data['is_approved'],
                ).select_related(
                    'employee__user',
                    'shop__settings__breaks',
                ).order_by('dt'))
                wds, w_types = copy_as_excel_cells(main_worker_days, employee_id, to_dates, created_by=request.user.id)

                created_wds.extend(wds)
                work_types.extend(w_types)

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
        with transaction.atomic():
            data = DeleteWorkerDaysSerializer(data=request.data, context={'request': request})
            data.is_valid(raise_exception=True)
            data = data.validated_data
            filt = {}
            if data['exclude_created_by']:
                filt['created_by__isnull'] = True
            WorkerDay.objects_with_excluded.filter(
                is_approved=False,
                is_fact=data['is_fact'],
                employee_id__in=data['employee_ids'],
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
        with transaction.atomic():
            data = ExchangeSerializer(data=request.data, context={'request': request})
            data.is_valid(raise_exception=True)
            data = data.validated_data
            data['is_approved'] = False
            data['user'] = request.user

            res = Response(WorkerDaySerializer(exchange(data, self.error_messages), many=True).data)

            WorkerDay.check_work_time_overlap(
                employee_id__in=[data['employee1_id'], data['employee2_id']],
                dt__in=data['dates'],
                exc_cls=ValidationError,
            )

        return res

    @swagger_auto_schema(
        request_body=ExchangeSerializer,
        operation_description='''
        Метод для обмена подтвержденными рабочими сменами
        ''',
        responses={200:WorkerDaySerializer(many=True)},
    )
    @action(detail=False, methods=['post'])
    def exchange_approved(self, request):
        with transaction.atomic():
            data = ExchangeSerializer(data=request.data, context={'request': request})
            data.is_valid(raise_exception=True)
            data = data.validated_data
            data['is_approved'] = True
            data['user'] = request.user

            res = Response(WorkerDaySerializer(exchange(data, self.error_messages), many=True).data)

            WorkerDay.check_work_time_overlap(
                employee_id__in=[data['employee1_id'], data['employee2_id']],
                dt__in=data['dates'],
                exc_cls=ValidationError,
            )

        return res

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
        request_body=GenerateUploadTimetableExampleSerializer,
        responses={200: 'Шаблон расписания в формате excel.'},
        operation_description='''
            Возвращает шаблон для загрузки графика.\n
            ''',
    )
    @action(detail=False, methods=['get'])
    def generate_upload_example(self, request):
        # TODO: рефакторинг + тест
        serializer = GenerateUploadTimetableExampleSerializer(
            data=request.query_params if request.method == 'GET' else request.data,
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)

        shop_id = serializer.validated_data.get('shop_id')
        dt_from = serializer.validated_data.get('dt_from')
        dt_to = serializer.validated_data.get('dt_to')
        is_fact = serializer.validated_data.get('is_fact')
        is_approved = serializer.validated_data.get('is_approved')
        employee_id__in = serializer.validated_data.get('employee_id__in')

        employee_qs = Employee.objects.filter(
            employments__id__in=Employment.objects.get_active(
                network_id=self.request.user.network_id,
                shop_id=shop_id,
                dt_from=dt_from,
                dt_to=dt_to,
                is_visible=True,
            )
        ).annotate(
            position=Subquery(Employment.objects.get_active(
                network_id=self.request.user.network_id,
                shop_id=shop_id,
                dt_from=dt_from,
                dt_to=dt_to,
                is_visible=True,
                employee_id=OuterRef('id'),
            ).order_by('-norm_work_hours').values('position__name')[:1])
        ).select_related(
            'user',
        ).order_by('user__last_name', 'user__first_name')

        if employee_id__in:
            employee_qs = employee_qs.filter(id__in=employee_id__in)

        wdays_dict = {f'{wd.employee_id}_{wd.dt}': wd for wd in WorkerDay.objects.filter(
            Q(Q(type__in=WorkerDay.TYPES_WITH_TM_RANGE) & Q(shop_id=shop_id)) |
            ~Q(type__in=WorkerDay.TYPES_WITH_TM_RANGE),
            employee__in=employee_qs,
            dt__gte=dt_from,
            dt__lte=dt_to,
            is_fact=is_fact,
            is_approved=is_approved,
        )}

        rows = []
        dates = list(
            pd.date_range(dt_from, dt_to).date)
        for employee in employee_qs:
            row_data = {}
            row_data[_('Employee id')] = employee.tabel_code
            row_data[_('Full name')] = employee.user.fio  # TODO: разделить на 3 поля
            row_data[_('Position')] = employee.position
            for dt in dates:
                _cell_value = ''

                wd = wdays_dict.get(f'{employee.id}_{dt}')
                if wd:
                    if wd.type in WorkerDay.TYPES_WITH_TM_RANGE:
                        tm_start = wd.dttm_work_start.strftime('%H:%M')
                        tm_end = wd.dttm_work_end.strftime('%H:%M')
                        _cell_value = f'{tm_start}-{tm_end}'
                    else:
                        _cell_value = WorkerDay.WD_TYPE_MAPPING.get(wd.type, '')

                row_data[dt] = _cell_value

            rows.append(row_data)

        df = pd.DataFrame(rows)

        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        sheet_name = _('Timetable')
        df.to_excel(
            excel_writer=writer, sheet_name=sheet_name, index=False,
            columns=[_('Employee id'), _('Full name'), _('Position')] + dates,
        )
        worksheet = writer.sheets[sheet_name]
        # set the column width as per your requirement
        for idx, col in enumerate(df):  # loop through all columns
            series = df[col]
            max_len = max((
                series.astype(str).map(len).max(),  # len of largest item
                len(str(series.name))  # len of column name/header
            )) + 2  # adding a little extra space
            worksheet.set_column(idx, idx, max_len)
        writer.save()
        output.seek(0)
        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="{}.xlsx"'.format(
            f'Timetable_{serializer.validated_data.get("shop_id")}_{dt_from}_{dt_to}')
        return response

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
        filename = _('Tabel_for_shop_{}_from_{}.{}').format(
            shop.code,
            timezone.now().strftime("%Y-%m-%d"),
            shop.network.convert_tabel_to or convert_to,
        )
        response['Content-Disposition'] = f'attachment; filename={escape_uri_path(filename)}'
        return response

    @swagger_auto_schema(
        request_body=BlockOrUnblockWorkerDayWrapperSerializer,
        responses={200: None},
        operation_description='''
            Заблокировать рабочий день.
            '''
    )
    @action(detail=False, methods=['post'], filterset_class=None)
    def block(self, request):
        serializer = BlockOrUnblockWorkerDayWrapperSerializer(
            data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        for dict_to_block in serializer.validated_data['worker_days']:
            WorkerDay.objects.filter(
                employee_id=dict_to_block['employee_id'],
                shop_id=dict_to_block['shop_id'],
                dt=dict_to_block['dt'],
                is_fact=dict_to_block['is_fact'],
            ).update(is_blocked=True)
        return Response()

    @swagger_auto_schema(
        request_body=BlockOrUnblockWorkerDayWrapperSerializer,
        responses={200: None},
        operation_description='''
            Разблокировать рабочий день.
            '''
    )
    @action(detail=False, methods=['post'], filterset_class=None)
    def unblock(self, request):
        serializer = BlockOrUnblockWorkerDayWrapperSerializer(
            data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        for dict_to_block in serializer.validated_data['worker_days']:
            WorkerDay.objects.filter(
                employee_id=dict_to_block['employee_id'],
                shop_id=dict_to_block['shop_id'],
                dt=dict_to_block['dt'],
                is_fact=dict_to_block['is_fact'],
            ).update(is_blocked=False)
        return Response()
