import datetime
import json
from itertools import groupby

import pandas as pd
from django.conf import settings
from django.contrib.postgres.aggregates import StringAgg
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import OuterRef, Subquery, Q, F, Exists, Case, When, Value, CharField
from django.db.models.functions import Concat, Cast
from django.db.models.query import Prefetch
from django.utils import timezone
from django.utils.functional import cached_property
from rest_framework.exceptions import PermissionDenied
from rest_framework.serializers import ValidationError

from src.base.models import Employment, Shop, Group
from src.events.signals import event_signal
from src.timetable.events import APPROVE_EVENT_TYPE
from src.timetable.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    ShopMonthStat,
    WorkerDayOutsourceNetwork,
    WorkerDayPermission,
    WorkerDayType,
    Restriction,
)
from src.timetable.timesheet.tasks import recalc_timesheet_on_data_change
from src.timetable.vacancy.tasks import vacancies_create_and_cancel_for_shop
from src.timetable.vacancy.utils import notify_vacancy_created
from src.timetable.worker_day.tasks import recalc_wdays, recalc_fact_from_records
from src.timetable.worker_day.utils.utils import check_worker_day_permissions


class WorkerDayApproveHelper:
    def __init__(self, is_fact, dt_from, dt_to, user=None, shop_id=None, employee_ids=None, wd_types=None,
                 approve_open_vacs=False, any_draft_wd_exists=False, exclude_approve_q=None):
        assert shop_id or employee_ids
        self.is_fact = is_fact
        self.dt_from = dt_from
        self.dt_to = dt_to
        self.user = user
        self.shop_id = shop_id
        self.employee_ids = employee_ids or []
        self._wd_types = wd_types
        self.approve_open_vacs = approve_open_vacs
        self.any_draft_wd_exists = any_draft_wd_exists
        self.exclude_approve_q = exclude_approve_q

    @cached_property
    def wd_types(self):
        return self._wd_types or list(WorkerDayType.objects.filter(
            is_active=True,
        ).values_list('code', flat=True))

    @cached_property
    def shop(self):
        if self.shop_id:
            return Shop.objects.filter(id=self.shop_id).select_related('network').first()

    @cached_property
    def wd_types_dict(self):
        return WorkerDayType.get_wd_types_dict()

    @staticmethod
    def remove_holidays(approved_workdays: pd.DataFrame):
        """Removing holidays in approve time if this day is workday.

        link: https://mindandmachine.myjetbrains.com/youtrack/issue/RND-521/Nekorrektnoe-sozdanie-smeny-podrabotchiku-esli-u-nego-vykhodnoi-den-v-osnovnom-grafike

        Workdays information about employee
        approved_workdays - pandas.Dataframe
            - columns
            - code
            - employee_id
            - dt
            - type_id
            - work_hours
            - dttm_work_start
            - dttm_work_end
            - shop_id
            - work_type_ids
            - is_vacancy

        Filtering type_id != H and check there are holidays in worksdays, are there - delete.
        :return:
        """
        workdays: pd.DataFrame = approved_workdays \
            .loc[approved_workdays['type_id'] != WorkerDay.TYPE_HOLIDAY] \
            .drop_duplicates()
        if len(workdays):
            holidays_workdays_for_delete_filter: Q = Q()
            for _, workday in workdays.iterrows():
                holidays_workdays_for_delete_filter |= Q(
                    type_id=WorkerDay.TYPE_HOLIDAY,
                    is_fact=False,  # Just for plan
                    **{field: workday.get(field) for field in ['code', 'employee_id', 'dt']}
                )
            WorkerDay.objects.filter(holidays_workdays_for_delete_filter).delete()

    def run(self):
        from src.timetable.worker_day.views import WorkerDayViewSet
        with transaction.atomic():
            allowed_wd_perms = check_worker_day_permissions(
                self.user,
                self.shop_id,
                WorkerDayPermission.APPROVE,
                WorkerDayPermission.FACT if self.is_fact else WorkerDayPermission.PLAN,
                self.wd_types,
                self.dt_from,
                self.dt_to,
                WorkerDayViewSet.error_messages,
                self.wd_types_dict,
            )
            today = (datetime.datetime.now() + datetime.timedelta(hours=3)).date()
            employee_filter = {}
            if self.employee_ids:
                employee_filter['employee_id__in'] = self.employee_ids
                employee_ids = self.employee_ids
            if self.shop:
                employee_ids = Employment.objects.get_active(
                    network_id=self.shop.network_id,
                    dt_from=self.dt_from,
                    dt_to=self.dt_to,
                    shop_id=self.shop_id,
                    **employee_filter,
                ).values_list('employee_id', flat=True)

            wd_types_grouped_by_limit = {}
            if self.user:
                for wd_type, limit_days_in_past, limit_days_in_future, employee_type, shop_type in allowed_wd_perms:
                    # Filtering by types, which are passed
                    if wd_type in self.wd_types:
                        wd_types_grouped_by_limit.setdefault((limit_days_in_past, limit_days_in_future), []).append(wd_type)
            else:
                for wd_type in self.wd_types:
                    wd_types_grouped_by_limit.setdefault((None, None), []).append(wd_type)
            wd_types_q = Q()
            for (limit_days_in_past, limit_days_in_future), wd_types in wd_types_grouped_by_limit.items():
                q = Q(type_id__in=wd_types)
                if limit_days_in_past or limit_days_in_future:
                    if limit_days_in_past:
                        q &= Q(dt__gte=today - datetime.timedelta(days=limit_days_in_past))
                    if limit_days_in_future:
                        q &= Q(dt__lte=today + datetime.timedelta(days=limit_days_in_future))
                wd_types_q |= q

            has_perm_to_approve_other_shop_days = self.user is None or Group.objects.filter(
                id__in=self.user.get_group_ids(shop_id=self.shop_id),
                has_perm_to_approve_other_shop_days=True,
            ).exists()

            shop_employees_q = Q(employee_id__in=employee_ids)
            if not has_perm_to_approve_other_shop_days:
                shop_employees_q &= Q(type__is_dayoff=True) | Q(type_id=WorkerDay.TYPE_QUALIFICATION)

            approve_condition: Q = Q(
                wd_types_q,
                Q(shop_id=self.shop_id) | shop_employees_q,
                dt__lte=self.dt_to,
                dt__gte=self.dt_from,
                is_fact=self.is_fact,
                **employee_filter,
            )
            columns = [
                'code',
                'employee_id',
                'dt',
                'type_id',
                'work_hours',
                'dttm_work_start',
                'dttm_work_end',
                'shop_id',
                'work_type_ids',
                'is_vacancy',
            ]
            draft_wdays = list(WorkerDay.objects.filter(
                approve_condition,
                is_approved=False,
            ).annotate(
                work_type_ids=StringAgg(
                    Cast('work_types', CharField()),
                    distinct=True,
                    delimiter=',',
                    output_field=CharField(),
                ),
            ).values_list(*columns))
            draft_df = pd.DataFrame(draft_wdays, columns=columns).drop_duplicates()

            approved_wdays_qs = WorkerDay.objects.filter(
                approve_condition,
                is_approved=True
            )
            if self.any_draft_wd_exists:
                approved_wdays_qs = approved_wdays_qs.filter(
                    Exists(
                        WorkerDay.objects.filter(
                            approve_condition,
                            Q(employee__isnull=False, employee_id=OuterRef('employee_id')),
                            is_approved=False,
                            dt=OuterRef('dt'),
                            is_fact=OuterRef('is_fact'),
                        ),
                    ),
                )
            approved_wdays = list(approved_wdays_qs.annotate(
                work_type_ids=StringAgg(
                    Cast('work_types', CharField()),
                    distinct=True,
                    delimiter=',',
                    output_field=CharField(),
                ),
            ).values_list(*columns))
            approved_df = pd.DataFrame(approved_wdays, columns=columns)

            combined_dfs = pd.concat([draft_df, approved_df]).drop_duplicates(keep=False)
            not self.is_fact and self.remove_holidays(combined_dfs)
            symmetric_difference = combined_dfs.astype(object)
            symmetric_difference.where(pd.notnull(symmetric_difference), None, inplace=True)
            employee_dt_pairs_list = list(
                symmetric_difference[['employee_id', 'dt']].sort_values(
                    ['employee_id', 'dt'], ascending=[True, True]
                ).values.tolist()
            )
            worker_dates_dict = {}
            for employee_id, dates_grouper in groupby(employee_dt_pairs_list, key=lambda i: i[0]):
                worker_dates_dict[employee_id] = tuple(i[1] for i in list(dates_grouper))

            transaction.on_commit(lambda: [cache.delete_pattern(f"prod_cal_*_*_{employee_id}") for employee_id in
                                           worker_dates_dict.keys()])

            if not employee_dt_pairs_list:
                # Nothing to approve
                return

            employee_days_q = Q()
            employee_days_set = set()
            for employee_id, dates in worker_dates_dict.items():
                employee_days_q |= Q(employee_id=employee_id, dt__in=dates)
                employee_days_set.add((employee_id, dates))

            wdays_to_approve = WorkerDay.objects.filter(
                employee_days_q,
                is_approved=False,
                is_fact=self.is_fact,

            )

            if self.exclude_approve_q:
                wdays_to_approve = wdays_to_approve.exclude(self.exclude_approve_q)

            # Don't approve opened vacancies
            if not self.approve_open_vacs:
                wdays_to_approve = wdays_to_approve.filter(employee_id__isnull=False)

            # если у пользователя нет группы с наличием прав на изменение защищенных дней, то проверяем,
            # что в списке подтверждаемых дней нет защищенных дней, если есть, то выдаем ошибку
            has_permission_to_change_protected_wdays = not self.user or Group.objects.filter(
                id__in=self.user.get_group_ids(shop_id=self.shop_id),
                has_perm_to_change_protected_wdays=True,
            ).exists()
            if not has_permission_to_change_protected_wdays:
                protected_wdays = list(WorkerDay.objects.filter(
                    employee_days_q, is_fact=self.is_fact,
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
                    dates=StringAgg(Cast('dt', CharField()), delimiter=',', ordering='dt'),
                ))
                if protected_wdays:
                    raise PermissionDenied(WorkerDayViewSet.error_messages['has_no_perm_to_approve_protected_wdays'].format(
                        protected_wdays=', '.join(
                            f'{d["employee_user_fio"]}: {d["dates"]}' for d in protected_wdays),
                    ))

            if not self.is_fact and settings.SEND_DOCTORS_MIS_SCHEDULE_ON_CHANGE:
                # TODO: при нескольких workerday скорее всего будет работать некорректно,
                #   должны ли мы это поддерживать?
                from src.celery.tasks import send_doctors_schedule_to_mis
                mis_data_qs = wdays_to_approve.annotate(
                    approved_wd_type_id=Subquery(WorkerDay.objects.filter(
                        dt=OuterRef('dt'),
                        employee_id=OuterRef('employee_id'),
                        is_fact=self.is_fact,
                        is_approved=True,
                    ).values('type_id')[:1]),
                    approved_wd_has_doctor_work_type=Exists(WorkerDayCashboxDetails.objects.filter(
                        worker_day__dt=OuterRef('dt'),
                        worker_day__employee_id=OuterRef('employee_id'),
                        worker_day__is_fact=self.is_fact,
                        worker_day__is_approved=True,
                        work_type__work_type_name__code='doctor',
                    )),
                    approved_wd_dttm_work_start=Subquery(WorkerDay.objects.filter(
                        dt=OuterRef('dt'),
                        employee_id=OuterRef('employee_id'),
                        is_fact=self.is_fact,
                        is_approved=True,
                    ).values('dttm_work_start')[:1]),
                    approved_wd_dttm_work_end=Subquery(WorkerDay.objects.filter(
                        dt=OuterRef('dt'),
                        employee_id=OuterRef('employee_id'),
                        is_fact=self.is_fact,
                        is_approved=True,
                    ).values('dttm_work_end')[:1]),
                ).filter(
                    Q(type_id=WorkerDay.TYPE_WORKDAY) | Q(approved_wd_type_id=WorkerDay.TYPE_WORKDAY),
                ).annotate(
                    action=Case(
                        When(
                            Q(
                                Q(approved_wd_type_id__isnull=True) | ~Q(
                                    approved_wd_type_id=WorkerDay.TYPE_WORKDAY),
                                type_id=WorkerDay.TYPE_WORKDAY,
                                work_types__work_type_name__code='doctor',
                            ),
                            then=Value('create', output_field=CharField())
                        ),
                        When(
                            Q(
                                ~Q(type_id=WorkerDay.TYPE_WORKDAY),
                                approved_wd_type_id=WorkerDay.TYPE_WORKDAY,
                                approved_wd_has_doctor_work_type=True,
                            ),
                            then=Value('delete', output_field=CharField()),
                        ),
                        When(
                            type_id=F('approved_wd_type_id'),
                            work_types__work_type_name__code='doctor',
                            approved_wd_has_doctor_work_type=True,
                            then=Value('update', output_field=CharField()),
                        ),
                        When(
                            type_id=F('approved_wd_type_id'),
                            work_types__work_type_name__code='doctor',
                            approved_wd_has_doctor_work_type=False,
                            then=Value('create', output_field=CharField()),
                        ),
                        When(
                            Q(
                                ~Q(work_types__work_type_name__code='doctor'),
                                type_id=F('approved_wd_type_id'),
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

            wdays_to_delete = WorkerDay.objects_with_excluded.filter(
                employee_days_q,
                is_fact=self.is_fact,
            ).exclude(
                id__in=wdays_to_approve.values_list('id', flat=True),
            ).exclude(
                employee_id__isnull=True,
            )
            if self.exclude_approve_q:
                wdays_to_delete = wdays_to_delete.exclude(self.exclude_approve_q)

            # If plan
            if not self.is_fact:
                # удаляется факт автоматический, связанный с удаляемым планом
                WorkerDay.objects.filter(
                    last_edited_by__isnull=True,
                    closest_plan_approved__in=wdays_to_delete,
                ).delete()

            wdays_to_delete.delete()
            vacancies_to_approve = list(wdays_to_approve.filter(is_vacancy=True, employee_id__isnull=True))
            wdays_to_approve.update(is_approved=True)
            WorkerDay.set_closest_plan_approved(
                q_obj=employee_days_q,
                is_approved=True if self.is_fact else None,
                delta_in_secs=self.shop.network.set_closest_plan_approved_delta_for_manual_fact if self.shop \
                    else self.user.network.set_closest_plan_approved_delta_for_manual_fact,
            )

            # если план, то выполним пересчет часов в ручных корректировках факта
            if not self.is_fact and self.user and self.user.network.only_fact_hours_that_in_approved_plan:
                wd_ids = list(WorkerDay.objects.filter(
                    employee_days_q,
                    last_edited_by__isnull=False,
                    is_fact=True,
                    type__is_dayoff=False,
                    dttm_work_start__isnull=False,
                    dttm_work_end__isnull=False,
                ).values_list('id', flat=True))
                if wd_ids:
                    recalc_wdays(id__in=wd_ids)

            approved_wds_list_qs = WorkerDay.objects.filter(
                    employee_days_q,
                    is_approved=True,
                    is_fact=self.is_fact,
                ).select_related(
                    'shop',
                    'employment',
                    'employment__position',
                    'employment__position__breaks',
                    'shop__settings__breaks',
                ).prefetch_related(
                    'worker_day_details',
                    Prefetch(
                        'outsources',
                        to_attr='outsources_list',
                    ),
                ).distinct()
            if self.exclude_approve_q:
                approved_wds_list_qs = approved_wds_list_qs.exclude(self.exclude_approve_q)  # TODO: тест
            approved_wds_list = list(approved_wds_list_qs)

            not_approved_wds_list = WorkerDay.objects.bulk_create(
                [
                    WorkerDay(
                        shop=approved_wd.shop,
                        employee_id=approved_wd.employee_id,
                        employment=approved_wd.employment,
                        work_hours=approved_wd.work_hours,
                        dttm_work_start=approved_wd.dttm_work_start,
                        dttm_work_end=approved_wd.dttm_work_end,
                        dt=approved_wd.dt,
                        is_fact=approved_wd.is_fact,
                        is_approved=False,
                        type=approved_wd.type,
                        created_by_id=approved_wd.created_by_id,
                        last_edited_by_id=approved_wd.last_edited_by_id,
                        is_vacancy=approved_wd.is_vacancy,
                        is_outsource=approved_wd.is_outsource,
                        comment=approved_wd.comment,
                        canceled=approved_wd.canceled,
                        need_count_wh=True,
                        is_blocked=approved_wd.is_blocked,
                        closest_plan_approved_id=approved_wd.closest_plan_approved_id,
                        parent_worker_day_id=approved_wd.id,
                        source=WorkerDay.SOURCE_ON_APPROVE,
                        code=approved_wd.code,
                    )
                    for approved_wd in approved_wds_list if approved_wd.employee_id
                    # не копируем день без сотрудника (вакансию) в неподтв. версию
                ]
            )
            search_wds = {}
            for not_approved_wd in not_approved_wds_list:
                search_wds[not_approved_wd.parent_worker_day_id] = not_approved_wd

            WorkerDayOutsourceNetwork.objects.bulk_create(
                [
                    WorkerDayOutsourceNetwork(
                        workerday=search_wds[approved_wd.id],
                        network=network,
                    )
                    for approved_wd in approved_wds_list if approved_wd.employee_id
                    for network in approved_wd.outsources_list
                ]
            )

            WorkerDayCashboxDetails.objects.bulk_create(
                [
                    WorkerDayCashboxDetails(
                        work_part=details.work_part,
                        worker_day=search_wds[approved_wd.id],
                        work_type_id=details.work_type_id,
                    )
                    for approved_wd in approved_wds_list if approved_wd.employee_id  # TODO: тест
                    for details in approved_wd.worker_day_details.all()
                ]
            )

            dttm_now = timezone.now()
            # если план
            if not self.is_fact:
                if self.shop:
                    # отмечаем, что график подтвержден
                    ShopMonthStat.objects.update_or_create(
                        shop_id=self.shop_id,
                        dt=self.dt_from.replace(day=1),
                        defaults=dict(
                            dttm_status_change=dttm_now,
                            is_approved=True,
                        )
                    )
                    WorkerDay.check_main_work_hours_norm(
                        dt_from=self.dt_from,
                        dt_to=self.dt_to,
                        employee_id__in=employee_ids,
                        shop_id=self.shop_id,
                        exc_cls=ValidationError,
                    )

                transaction.on_commit(
                    lambda: recalc_fact_from_records(employee_days_list=list(employee_days_set)))

                if self.shop:
                    transaction.on_commit(
                        lambda: vacancies_create_and_cancel_for_shop.delay(self.shop_id))

                def _notify_vacancies_created():
                    for vacancy in vacancies_to_approve:
                        notify_vacancy_created(vacancy, is_auto=False)

                transaction.on_commit(lambda: _notify_vacancies_created())
                if not has_permission_to_change_protected_wdays:
                    WorkerDay.check_tasks_violations(
                        employee_days_q=employee_days_q,
                        is_approved=True,
                        is_fact=self.is_fact,
                        exc_cls=ValidationError,
                    )

            approve_event_context = {
                'is_fact': self.is_fact,
                'shop_id': self.shop_id,
                'employee_ids': self.employee_ids,
                'dt_from': self.dt_from,
                'dt_to': self.dt_to,
                'approve_open_vacs': self.approve_open_vacs,
                'wd_types': self.wd_types,
            }
            transaction.on_commit(lambda: event_signal.send(
                sender=None,
                network_id=self.user.network_id if self.user else self.shop.network_id,
                event_code=APPROVE_EVENT_TYPE,
                user_author_id=self.user.id if self.user else None,
                shop_id=self.shop_id,
                context=approve_event_context,
            ))

            recalc_timesheet_on_data_change(worker_dates_dict)

            WorkerDay.check_work_time_overlap(
                employee_days_q=employee_days_q,
                exc_cls=ValidationError,
            )
            Restriction.check_restrictions(
                employee_days_q=employee_days_q,
                is_fact=self.is_fact,
                is_approved=True,
                exc_cls=ValidationError,
            )
