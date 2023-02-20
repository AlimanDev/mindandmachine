import json, itertools
from typing import Union, Iterable, Iterator
from datetime import date

import pandas as pd
from django.conf import settings
from django.contrib.postgres.aggregates import StringAgg
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import OuterRef, Subquery, Q, F, Exists, Case, When, Value, CharField, QuerySet, Model
from django.db.models.functions import Cast
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext as _
from rest_framework.exceptions import PermissionDenied
from rest_framework.serializers import ValidationError

from src.abstract.services.service import Service
from src.base.models import Employment, Shop, Group
from src.celery.tasks import send_doctors_schedule_to_mis
from src.events.signals import event_signal
from src.timetable.events import APPROVE_EVENT_TYPE, APPROVED_NOT_FIRST_EVENT
from src.timetable.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    ShopMonthStat,
    WorkerDayOutsourceNetwork,
    WorkerDayPermission,
    GroupWorkerDayPermission,
    WorkerDayType,
    Restriction
)
from src.timetable.timesheet.tasks import recalc_timesheet_on_data_change
from src.timetable.vacancy.tasks import vacancies_create_and_cancel_for_shop
from src.timetable.vacancy.utils import notify_vacancy_created
from src.timetable.worker_day.tasks import recalc_work_hours, recalc_fact_from_records
from src.timetable.worker_day_permissions.checkers import BaseWdPermissionChecker
from src.timetable.exceptions import ApprovalError, NothingToApprove
from src.timetable.worker_day.utils.utils import ERROR_MESSAGES


class WorkerDayApproveService(Service):
    # To compare draft to approved days for changes
    DIFFERENCE_FIELDS = (
        'code',
        'employee_id',
        'dt',
        'type_id',
        'work_hours',
        'dttm_work_start',
        'dttm_work_end',
        'shop_id',
        'work_type_ids',
        'is_vacancy'
    )
    VALUES = DIFFERENCE_FIELDS + ('id', 'is_approved')
    # To remove holidays from draft, to 'approve_not_first' filter
    COMPARISON_FIELDS = ('employee_id', 'dt')
    # Order inside notification
    NOT_APPROVED_FIRST_ORDER_BY = (
        'employee__user__last_name',
        'employee__user__first_name',
        'employee__user__middle_name',
        'dt',
        'parent_worker_day__dttm_work_start'
    )


    def __init__(
            self, is_fact, dt_from, dt_to, user=None, shop_id=None, employee_ids=None, 
            wd_types=None, approve_open_vacs=False, exclude_approve_q=None):
        assert shop_id or employee_ids
        self.is_fact = is_fact
        self.dt_from = dt_from
        self.dt_to = dt_to
        self.user = user
        self.shop_id = shop_id
        self.request_employee_ids = employee_ids or []
        self._wd_types = wd_types
        self.approve_open_vacs = approve_open_vacs
        self.exclude_approve_q = exclude_approve_q

    # Public interface
    def approve(self) -> int:
        """
            Approve WorkerDays. Returns number of approved WorkerDays.
            Running without user is only for programmatic use - skips a lot of permission checks.
        """
        try:
            return self._run()
        except NothingToApprove:
            return 0
        except Shop.DoesNotExist:
            raise ValidationError(_('No shop found for id {shop_id}').format(shop_id=self.shop_id))


    # Main function
    @transaction.atomic
    def _run(self) -> int:
        draft_wdays, approved_wdays = self._get_wdays()
        self._parse_changes_in_wdays(draft_wdays, approved_wdays)
        self._filter_wdays(draft_wdays, approved_wdays)
        self._parse_for_approval(draft_wdays)
        self._parse_for_deletion()

        ###### Orteka custom logic =( ######
        if self.to_approve_wdays:
            if not self.is_fact:
                self._remove_holidays()
            if self.user and self.shop:
                self._handle_approved_not_first()
            if not self.is_fact and settings.SEND_DOCTORS_MIS_SCHEDULE_ON_CHANGE:
                self._send_doctors_mis_schedule_on_change()
        ####################################

        self._parse_wdays()

        if self.user:
            self._check_permissions()

        if not self.is_fact:
            self._delete_closest_automatic_fact() 
        self._delete_approved_wdays()
        approved_count = self._approve_wdays()
 
        self._post_approve_checks()
        self._post_approve_actions()
        self._post_approve_events()

        return approved_count


    # Reusable values
    @cached_property
    def approve_condition(self):
        """`Q()` lookup for WorkerDays, without `is_approved` field"""
        return self.condition & Q(is_fact=self.is_fact)

    @cached_property
    def condition(self):
        """`Q()` lookup for WorkerDays, without `is_approved` and `is_fact` fields"""
        shop_employees_q = Q(employment__in=self.current_employments)
        approve_other_shops = not self.user or \
            not self.shop and \
            Group.objects.filter(
                id__in=self.user_groups,
                has_perm_to_approve_other_shop_days=True,
            ).exists()
        if not approve_other_shops:
            shop_employees_q &= Q(type__is_dayoff=True) | Q(type_id=WorkerDay.TYPE_QUALIFICATION)

        approve_condition = Q(
            Q(shop_id=self.shop_id) | shop_employees_q,
            type_id__in=self.requested_wd_types,
            dt__range=(self.dt_from, self.dt_to),
        )
        if self.request_employee_ids:
            approve_condition &= Q(employee_id__in=self.request_employee_ids)
        if not self.approve_open_vacs:  # Don't approve opened vacancies
            approve_condition &= Q(employee__isnull=False)
        if self.exclude_approve_q:
            approve_condition &= ~self.exclude_approve_q
        return approve_condition

    @cached_property
    def current_employments(self) -> QuerySet[Employment]:
        """For finding days, that are not tied to shop (e.g. holidays, vacations)"""
        queryset = Employment.objects.get_active(
            dt_from=self.dt_from,
            dt_to=self.dt_to
        )
        if self.shop:
            queryset = queryset.filter(shop=self.shop)
        return queryset

    @cached_property
    def shop(self) -> Union[Shop, None]:
        if not self.shop_id:
            return
        return Shop.objects.select_related('network').get(id=self.shop_id)

    @cached_property
    def requested_wd_types(self) -> Iterable[str]:
        requested_wd_types = self._wd_types or tuple(WorkerDayType.objects.filter(
            is_active=True,
        ).values_list('code', flat=True))
        if not requested_wd_types:
            raise ValidationError(
                ERROR_MESSAGES['no_wd_types'].format(
                    action_str=WorkerDayPermission.ACTIONS_DICT.get(WorkerDayPermission.APPROVE).lower()
                    )
                )
        return requested_wd_types

    @cached_property
    def changes_dict(self) -> Q:
        return self.__get_employee_days_dict(
            itertools.chain(self.changed_draft_wdays, self.changed_approved_wdays)
        )

    @cached_property
    def changes_q(self) -> dict[int, set[date]]:
        return self.__get_employee_days_q(self.changes_dict)

    @cached_property
    def employee_days_dict(self) -> dict[int, set[date]]:
        return self.__get_employee_days_dict(self.to_approve_wdays)

    @cached_property
    def employee_days_q(self) -> Q:
        return self.__get_employee_days_q(self.employee_days_dict)

    @cached_property
    def permission_to_change_protected_wdays(self) -> bool:
        return Group.objects.filter(
            id__in=self.user_groups,
            has_perm_to_change_protected_wdays=True,
        ).exists()

    @cached_property
    def user_groups(self) -> list:
        return self.user.get_group_ids(shop_id=self.shop_id)

    @property
    def all_days(self) -> Iterable[WorkerDay]:
        return itertools.chain(self.to_approve_wdays, self.to_delete_wdays)


    # Day parsing
    def _get_wdays(self) -> tuple[tuple[WorkerDay], tuple[WorkerDay]]:
        """Get draft and approved WorkerDays from DB"""
        draft_wdays = tuple(
            WorkerDay.objects.filter(
                self.approve_condition,
                is_approved=False,
            ).annotate(
                work_type_ids=StringAgg(
                    Cast('work_types', CharField()),
                    distinct=True,
                    delimiter=',',
                    output_field=CharField(),
                )
            ).select_related(
                'employment',
                'employment__position',
                'employment__position__breaks',
                'employment__employee',
                'employment__employee__user',
                'employment__shop',
                'employee__user',
                'parent_worker_day',
                'parent_worker_day__type',
                'shop',
                'shop__network',
                'shop__settings__breaks',
                'type',
            ).prefetch_related(
                'worker_day_details',
                'outsources'
            )
        )
        approved_wdays = tuple(
            WorkerDay.objects.filter(
                self.approve_condition,
                is_approved=True,
            ).exclude(
                is_vacancy=True, employee_id__isnull=True    # don't delete open vacs
            ).annotate(
                work_type_ids=StringAgg(
                    Cast('work_types', CharField()),
                    distinct=True,
                    delimiter=',',
                    output_field=CharField(),
                )
            )
        )
        if not draft_wdays and not approved_wdays:
            raise NothingToApprove
        return draft_wdays, approved_wdays

    def _parse_changes_in_wdays(
            self, draft_wdays: tuple[WorkerDay], approved_wdays: tuple[WorkerDay]
            ):
        """Compare draft and approved WorkerDays for `DIFFERENCE_FIELDS`, find actual changes, return to_approve_ids and to_delete_ids"""
        # Model to dict (only fields in VALUES)
        draft_data = self.__models_to_dict(draft_wdays, self.VALUES)
        approved_data = self.__models_to_dict(approved_wdays, self.VALUES)

        # Combined DataFrame with all days
        draft_df = pd.DataFrame(draft_data)
        approved_df = pd.DataFrame(approved_data)
        combined_dfs = pd.concat([draft_df, approved_df])

        # Drop duplicates by specific field to find actual changes.
        # TODO: think of another way of logical comparison. This does not allow full duplicates in draft.
        symmetric_difference = combined_dfs.drop_duplicates(subset=self.DIFFERENCE_FIELDS, keep=False).astype(object)

        # Similar open vacancies can be dropped as duplicates. Forcefully add them back in.
        if not draft_df.empty:
            open_vacancies = draft_df.loc[(draft_df['employee_id'].isnull()) & (draft_df['is_vacancy'] == True)]
            symmetric_difference = pd.concat([symmetric_difference, open_vacancies]).astype(object)

        # NaN to None
        symmetric_difference.where(pd.notnull(symmetric_difference), None, inplace=True)

        # Split by is_approved. False (draft) will be approved, True (currently approved) will be deleted.
        grouped = symmetric_difference.groupby('is_approved')

        # Draft - to approve
        if False in grouped.groups:
            self.changed_draft_ids = set(grouped.get_group(False)['id'])
        else:
            self.changed_draft_ids = set()

        # Approved - to delete
        if True in grouped.groups:
            self.changed_approved_ids = set(grouped.get_group(True)['id'])
        else:
            self.changed_approved_ids = set()

        if not self.changed_draft_ids and not self.changed_approved_ids:
            raise NothingToApprove

    def _filter_wdays(
            self, draft_wdays: tuple[WorkerDay], approved_wdays: tuple[WorkerDay]
            ):
        """
        Filter wdays.
        Draft: by changes_dict (employee-dt)
        Approved: by `changed_draft_ids` and `changed_approved_ids`
        """
        self.changed_draft_wdays = tuple(filter(lambda wd: wd.id in self.changed_draft_ids, draft_wdays))
        self.changed_approved_wdays = tuple(filter(lambda wd: wd.id in self.changed_approved_ids, approved_wdays))

    def _parse_for_approval(self, draft_wdays: Iterable[WorkerDay]):
        """
        Prepares tuples of days and ids for approval. `draft_wdays` filtered by employee-dt
        """
        filter_func = lambda wd: wd.dt in self.changes_dict.get(wd.employee_id, set())
        self.to_approve_wdays = tuple(filter(filter_func, draft_wdays))
        self.to_approve_ids = {wd.id for wd in self.to_approve_wdays}

    def _parse_for_deletion(self):
        """
        Prepares tuples of tdays and ids for deletion. `changed_approved_wdays` + queried by employee-dt
        If day is in either to_approve or to_delete - all of the WorkerDays in approved table for that employee-dt should be deleted.
        Examples:
        1. Empty draft should overwrite any days in approved table.
        2. If 1 day type is going to be approved - all day types in approved table should be deleted
        3. If any small change is found in 1 of 3 days in draft - 2 are left as draft,
           that 1 day will be approved and all days in approved table are deleted.
        """
        wdays = WorkerDay.objects.filter(
            self.changes_q,
            is_approved=True,
            is_fact=self.is_fact
        ).exclude(
            is_vacancy=True, employee_id__isnull=True                # don't delete open vacancies
        )
        if self.shop:
            wdays = wdays.filter(Q(shop=self.shop) | Q(shop__isnull=True))  # don't delete days in other shops
        self.to_delete_wdays = self.changed_approved_wdays + tuple(filter(lambda wd: wd.id not in self.changed_approved_ids, wdays))
        self.to_delete_ids = {wd.id for wd in self.to_delete_wdays}


    # Orteka custom logic
    def _remove_holidays(self):
        """
        Orteka-specific.
        Deleting holidays in draft if there are other day types in the same day draft.
        E.g. if you try to approve TYPE_WORKDAY and TYPE_HOLIDAY for the same employee, date and code,
        holiday will not be approved and will be deleted from draft instead.
        """

        # key - tuple[COMPARISON_FIELDS], value - WorkerDay
        other_days_dict = {self.__day_key(wd): wd for wd in self.to_approve_wdays if wd.type_id != WorkerDay.TYPE_HOLIDAY}
        holidays = tuple(filter(lambda wd: wd.type_id == WorkerDay.TYPE_HOLIDAY, self.to_approve_wdays))
        holidays_to_delete_ids = {holiday.id for holiday in holidays if self.__day_key(holiday) in other_days_dict}

        # Move holidays from to_approve_* to to_delete_*
        self.to_approve_ids.difference_update(holidays_to_delete_ids)
        self.to_approve_wdays = tuple(filter(lambda wd: wd.id in self.to_approve_ids, self.to_approve_wdays))
        self.to_delete_ids.update(holidays_to_delete_ids)
        self.to_delete_wdays = self.to_delete_wdays + holidays

    def _handle_approved_not_first(self):
        """
        Orteka-specific.
        "Approved not first" filter. Exclude days that have parent_worker_day.
        Send notification to manager (УРС).
        """
        # Check GroupWorkerDayPermissions for `allow_approve_first`,
        # gather day types that shouldn't be approved if they are first (no parent day)
        # TODO: combine GWDP requests in one. See src.timetable.worker_day_permissions.checkers.BaseWdPermissionChecker._get_group_wd_permissions
        not_first_types = set(
            GroupWorkerDayPermission.objects.filter(
                allow_approve_first=False,
                group__in=self.user_groups,
                worker_day_permission__action=WorkerDayPermission.APPROVE,
                worker_day_permission__graph_type=WorkerDayPermission.FACT if self.is_fact else WorkerDayPermission.PLAN,
                worker_day_permission__wd_type_id__in=self.requested_wd_types
            ).values_list('worker_day_permission__wd_type__code', flat=True)
        )
        if not not_first_types:
            return

        # Exclude days that are first (no parent day).
        # If such day is found in draft - both other draft days and days for deletion
        # will be excluded from the scope (compared by `__day_key()`)
        # Example: 2 drafts, 1 day in approved. One of the drafts can't be approved,
        # since it doesn't have a parent day. So all 3 days will remain untouched,
        # even if the second draft day was perfectly fine for approval.
        exclude_keys = set()
        for wd in self.to_approve_wdays:
            if wd.type_id in not_first_types and not wd.parent_worker_day_id:
                exclude_keys.add(self.__day_key(wd))

        # don't approve draft days
        self.to_approve_wdays = tuple(filter(
            lambda wd: self.__day_key(wd) not in exclude_keys,
            self.to_approve_wdays
        ))
        if not self.to_approve_wdays:
            raise NothingToApprove
        self.to_approve_ids = set(wd.id for wd in self.to_approve_wdays)

        # don't delete approved days
        self.to_delete_wdays = tuple(filter(
            lambda wd: self.__day_key(wd) not in exclude_keys,
            self.to_delete_wdays
        ))
        self.to_delete_ids = set(wd.id for wd in self.to_delete_wdays)

        self._send_notification_approved_not_first(not_first_types)

    def _send_notification_approved_not_first(self, not_first_types: set[str]):
        # Schedule notifications. EventEmailNotification (or other notification type)
        # will be used for templating, recipients etc.
        not_first_approved_days = filter(
            lambda wd: wd.type_id in not_first_types and wd.parent_worker_day,
            self.to_approve_wdays
        )
        not_first_approved_days_values = list(
            {
                'employee__user__first_name': wd.employee.user.first_name,
                'employee__user__middle_name': wd.employee.user.middle_name,
                'employee__user__last_name': wd.employee.user.last_name,
                'dt': wd.dt,
                'dttm_work_start': wd.dttm_work_start,
                'dttm_work_end': wd.dttm_work_end,
                'type__name': wd.type.name,
                'parent_worker_day__dttm_work_start': wd.parent_worker_day.dttm_work_start,
                'parent_worker_day__dttm_work_end': wd.parent_worker_day.dttm_work_end,
                'parent_worker_day__type__name': wd.parent_worker_day.type.name
            }
            for wd in not_first_approved_days
        )
        if not not_first_approved_days_values:
            return
        not_first_approved_days_values.sort(
            key=lambda wd: tuple(wd.get(key) for key in self.NOT_APPROVED_FIRST_ORDER_BY)
        )
        context = {
            'is_fact': self.is_fact,
            'shop_id': self.shop_id,
            'wdays': not_first_approved_days_values
        }
        transaction.on_commit(
            lambda: event_signal.send(
                sender=None,
                network_id=self.shop.network_id,
                event_code=APPROVED_NOT_FIRST_EVENT,
                user_author_id=self.user.id,
                context=context
            )
        )

    def _send_doctors_mis_schedule_on_change(self):
        """Orteka-specific. Schedules task `send_doctors_schedule_to_mis`."""
        # TODO: при нескольких workerday скорее всего будет работать некорректно,
        #   должны ли мы это поддерживать?
        # TODO: rewrite to in-memory comparison and move to `_post_approve_actions`
        mis_data_qs = WorkerDay.objects.filter(
            id__in=self.to_approve_ids
        ).annotate(
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
        if not mis_data_qs:
            return
        mis_data = []
        for d in mis_data_qs:
            if d['action'] == 'delete':
                d['dttm_work_start'] = d['approved_wd_dttm_work_start']
                d['dttm_work_end'] = d['approved_wd_dttm_work_end']
            d.pop('approved_wd_dttm_work_start')
            d.pop('approved_wd_dttm_work_end')
            mis_data.append(d)
        json_data = json.dumps(mis_data, cls=DjangoJSONEncoder)
        transaction.on_commit(
            lambda f_json_data=json_data: send_doctors_schedule_to_mis.delay(json_data=f_json_data)
        )


    # Parsing
    def _parse_wdays(self):
        """Parse data from to_approve_wdays and to_delete_wdays"""
        self._parse_to_approve_wdays()
        self._parse_to_delete_wdays()

    def _parse_to_approve_wdays(self):
        """Parse employees, employments and wd_types from to_approve_wdays."""
        self.employee_ids_for_approval = set()
        self.employments_for_approval = set()
        self.wd_types_ids_for_approval = set()
        # which employment has which day types for specific date range
        # {employment_id: {wd_type_id: {dates}}}
        self.employments_for_approval_wd_types_dict: dict[int, dict[str, set]] = {} 
        for wd in self.to_approve_wdays:
            self.wd_types_ids_for_approval.add(wd.type_id)
            if wd.employee_id:
                self.employee_ids_for_approval.add(wd.employee_id)
            if wd.employment:
                self.employments_for_approval.add(wd.employment)
                type_dict: dict = self.employments_for_approval_wd_types_dict.setdefault(wd.employment.id, {})
                type_dict.setdefault(wd.type_id, set()).add(wd.dt)

    def _parse_to_delete_wdays(self):
        """
        Parse employments and wd_types from to_delete_wdays, splitting them into:
        1. Days that are updated/changed (day type is preserved)
        2. Days that are truly deleted (draft has other day type or blank)
        Both will be deleted from DB, but this is important for permissions checks.
        """
        self.employments_for_updating: set[Employment] = set()
        self.employments_for_true_deletion: set[Employment] = set()
        # which employment has which day types for specific date range
        # {employment_id: {wd_type_id: (dt_from, dt_to)}}
        self.employments_for_updating_wd_types_dict: dict[int, dict[str, set]] = {}
        self.employments_for_true_deletion_wd_types_dict: dict[int, dict[str, set]] = {}
        for wd in self.to_delete_wdays:
            if not wd.employment:
                continue
            elif wd.dt in self.employments_for_approval_wd_types_dict.get(wd.employment.id, {}).get(wd.type_id, set()):
                # same day type in draft -> something is updating/changing in the day
                self.employments_for_updating.add(wd.employment)
                type_dict: dict = self.employments_for_updating_wd_types_dict.setdefault(wd.employment.id, {})
            else:
                # type not in draft -> day is deleted/overwritten by another type
                self.employments_for_true_deletion.add(wd.employment)
                type_dict: dict = self.employments_for_true_deletion_wd_types_dict.setdefault(wd.employment.id, {})
            type_dict.setdefault(wd.type_id, set()).add(wd.dt)


    # Permmissions
    def _check_permissions(self):
        """All possible permission-related checks. Raises PermissionDenied (403 Forbidden)."""
        checker = BaseWdPermissionChecker(
            self.user,
            shop=self.shop,
            check_active_empl=False
        )
        self.open_vac_perm = self._check_permission_open_vacancies(checker)  # raises if not perm
        self._check_empty_employments()
        self._check_permission_protected_wdays()
        self._check_group_permissions_to_approve(checker)
        self._check_group_permissions_to_update(checker)
        self._check_group_permissions_to_delete(checker)

    def _check_permission_open_vacancies(self, checker: BaseWdPermissionChecker) -> Union[bool, None]:
        """
            `True` - has permission and there are open vacancies to be approved
            Raises if doesn't have permission and there are open vacancies to be approved
            `None` - no open vacancies
        """
        if not self.approve_open_vacs:
            return
        vacancies_types = {wd.type_id for wd in self.to_approve_wdays if wd.is_open_vacancy}
        if not vacancies_types:
            return
        for wd_type in vacancies_types:
            permission = checker.has_group_permission(
                action=WorkerDayPermission.APPROVE,
                graph_type=WorkerDayPermission.FACT if self.is_fact else WorkerDayPermission.PLAN,
                wd_type_id=wd_type,
                dt_from=self.dt_from,
                dt_to=self.dt_to,
                is_vacancy=True
            )
            if not permission:
                raise PermissionDenied(checker.err_message)
        return True

    def _check_empty_employments(self) -> bool:
        """Various checks when employments_for_approval are empty"""
        if self.employments_for_approval or self.employments_for_true_deletion:
            # Employments = there are normal days to approve
            return True
        if self.to_approve_wdays and self.open_vac_perm and all(wd.is_open_vacancy for wd in self.to_approve_wdays):
            # Only open vacancies in draft
            return True
        elif not self.to_approve_wdays and self.to_delete_wdays:
            # No days to approve, but some days need to be deleted (draft is empty)
            return True

        # Shouldn't happen. Throws 500 just in case. Needs further observation.
        raise ApprovalError(
            f'No employments and not all open vacancies. to_approve_ids: {self.to_approve_ids}, to_delete_ids: {self.to_delete_ids}'
        )

    def _check_permission_protected_wdays(self) -> bool:
        """
        Check user Group for permission to change protected days.
        Raises if doesn't have and there are protected days.
        """
        if not self.permission_to_change_protected_wdays and any(wd.is_blocked for wd in self.all_days):
            raise PermissionDenied(ERROR_MESSAGES['has_no_perm_to_approve_protected_wdays'].format(
                protected_wdays=', '.join(
                    f'{wd.employee.user.fio}: {wd.dt}' for wd in self.all_days if wd.is_blocked),
            ))
        return True

    def _check_group_permissions_to_approve(self, checker: BaseWdPermissionChecker) -> Union[bool, None]:
        """`GroupWorkerDayPermissions` for APPROVE action"""
        if not all((self.to_approve_wdays, self.employments_for_approval, self.employments_for_approval_wd_types_dict)):
            return
        return self.__check_group_permissions(
            checker, self.employments_for_approval, self.employments_for_approval_wd_types_dict, WorkerDayPermission.APPROVE
        )

    def _check_group_permissions_to_update(self, checker: BaseWdPermissionChecker) -> Union[bool, None]:
        """`GroupWorkerDayPermissions` for UPDATE action"""
        if not all((self.to_delete_wdays, self.employments_for_updating, self.employments_for_updating_wd_types_dict)):
            return
        return self.__check_group_permissions(
            checker, self.employments_for_updating, self.employments_for_updating_wd_types_dict, WorkerDayPermission.UPDATE
        )

    def _check_group_permissions_to_delete(self, checker: BaseWdPermissionChecker) -> Union[bool, None]:
        """`GroupWorkerDayPermissions` for DELETE action"""
        if not all((self.to_delete_wdays, self.employments_for_true_deletion, self.employments_for_true_deletion_wd_types_dict)):
            return
        return self.__check_group_permissions(
            checker, self.employments_for_true_deletion, self.employments_for_true_deletion_wd_types_dict, WorkerDayPermission.DELETE
        )

    def __check_group_permissions(
            self,
            checker: BaseWdPermissionChecker,
            employments: Iterable[Employment],
            employments_wd_type_dict: dict[int, dict[str, set]],
            action: str
            ) -> bool:
        for employment in employments:
            for wd_type_id, dates in employments_wd_type_dict[employment.id].items():
                dt_from, dt_to = min(dates), max(dates)
                permission = checker.has_group_permission(
                    employment=employment,
                    action=action,
                    graph_type=WorkerDayPermission.FACT if self.is_fact else WorkerDayPermission.PLAN,
                    wd_type_id=wd_type_id,
                    dt_from=dt_from,
                    dt_to=dt_to,
                    is_vacancy=False
                )
                if not permission:
                    raise PermissionDenied(checker.err_message)
        return True


    # Approval
    def _delete_closest_automatic_fact(self) -> tuple[int, dict[str, int]]:
        """Delete automatic fact days that are connected to plan to_delete_wdays"""
        if not self.to_delete_wdays:
            return (0, {})
        return WorkerDay.objects.filter(
            last_edited_by__isnull=True,
            closest_plan_approved__in=self.to_delete_ids,
        ).delete()

    def _delete_approved_wdays(self) -> tuple[int, dict[str, int]]:
        if not self.to_delete_wdays:
            return (0, {})
        return WorkerDay.objects.filter(id__in=self.to_delete_ids).delete()

    def _approve_wdays(self) -> int:
        if not self.to_approve_wdays:
            return 0
        return WorkerDay.objects.filter(id__in=self.to_approve_ids).update(is_approved=True)


    # Checks
    def _post_approve_checks(self):
        """Various checks, that can raise errors and rollback the transaction"""
        if not self.to_approve_wdays:
            return
        if not self.is_fact:
            if self.shop:
                self._check_main_work_hours_norm()
            if not self.permission_to_change_protected_wdays:
                self._check_tasks_violations()
        self._check_work_time_overlap()
        self._check_restrictions()

    def _check_main_work_hours_norm(self):
        """Checks that new days do not conflict with norm schedule. Raises error that rollbacks the transaction."""
        # TODO: refactor to in-memory. This grabs all days from BD, not just approved ones
        WorkerDay.check_main_work_hours_norm(
            dt_from=self.dt_from,
            dt_to=self.dt_to,
            employee_id__in=self.employee_ids_for_approval,
            shop_id=self.shop_id,
            exc_cls=ValidationError,
        )

    def _check_tasks_violations(self):
        """Checks that new schedule doesn't conflict with Tasks (e.g. Task may not be left outside working hours."""
        # TODO: refactor to in-memory. This grabs all days from BD, not just approved ones
        WorkerDay.check_tasks_violations(
            is_fact=self.is_fact,
            employee_days_q=self.employee_days_q,
            is_approved=True,
            exc_cls=ValidationError,
        )

    def _check_work_time_overlap(self):
        WorkerDay.check_work_time_overlap(
            employee_days_q=self.employee_days_q,
            exc_cls=ValidationError,
        )

    def _check_restrictions(self):
        Restriction.check_restrictions(
            employee_days_q=self.employee_days_q,
            is_fact=self.is_fact,
            is_approved=True,
            exc_cls=ValidationError,
        )


    # Actions
    def _post_approve_actions(self):
        """Various things to be done after approval"""
        if not self.is_fact:
            if self.user and self.user.network.only_fact_hours_that_in_approved_plan:
                self._recalc_work_hours()
            if self.shop:
                self._update_shop_stat()
                self._create_and_cancel_vacancies()
        if not self.to_approve_wdays:
            return
        self._set_closest_plan_approved()
        if not self.is_fact:
            self._recalc_fact_from_records()    # after _set_closest_plan_approved
        self._create_draft()
        self._recalc_timesheet()
        self._delete_cache()

    def _recalc_work_hours(self):
        """For plan, recalc work hours in manual fact changes"""
        if not self.to_approve_wdays:
            return
        to_recalc_ids = tuple(
            WorkerDay.objects.filter(
                self.condition,
                last_edited_by__isnull=False,
                is_fact=True,
                type__is_dayoff=False,
                dttm_work_start__isnull=False,
                dttm_work_end__isnull=False,
            ).values_list('id', flat=True)
        )
        if to_recalc_ids:
            recalc_work_hours(id__in=to_recalc_ids)

    def _update_shop_stat(self):
        """Mark ShopMonthStat as approved"""
        ShopMonthStat.objects.update_or_create(
            shop_id=self.shop_id,
            dt=self.dt_from.replace(day=1),
            defaults=dict(
                dttm_status_change=timezone.now(),
                is_approved=True,
            )
        )

    def _create_and_cancel_vacancies(self):
        transaction.on_commit(
            lambda: vacancies_create_and_cancel_for_shop.delay(self.shop_id)
        )

    def _set_closest_plan_approved(self):
        #TODO: research this method, maybe refactor
        if self.is_fact:    # Set closest plan for the newly approved fact
            q = Q(id__in=self.to_approve_ids)
            is_approved=True
        else:               # Link this approved plan to existing fact
            q = self.employee_days_q
            is_approved=None
        WorkerDay.set_closest_plan_approved(
            q_obj=q,
            is_approved=is_approved,
            delta_in_secs=self.shop.network.set_closest_plan_approved_delta_for_manual_fact if self.shop \
                else self.user.network.set_closest_plan_approved_delta_for_manual_fact,
        )

    def _recalc_fact_from_records(self):
        transaction.on_commit(
            lambda: recalc_fact_from_records(employee_days_list=self.employee_days_dict.items())
        )

    def _create_draft(self):
        """
        Create corresponding draft WorkerDay, WorkerDayOutsourceNetwork, WorkerDayCashboxDetails.
        Doesn't copy open vacancies.
        """
        new_draft_wdays = WorkerDay.objects.bulk_create(
            (
                WorkerDay(
                    shop=wd.shop,
                    employee_id=wd.employee_id,
                    employment=wd.employment,
                    work_hours=wd.work_hours,
                    dttm_work_start=wd.dttm_work_start,
                    dttm_work_end=wd.dttm_work_end,
                    dt=wd.dt,
                    is_fact=wd.is_fact,
                    is_approved=False,
                    type=wd.type,
                    created_by_id=wd.created_by_id,
                    last_edited_by_id=wd.last_edited_by_id,
                    is_vacancy=wd.is_vacancy,
                    is_outsource=wd.is_outsource,
                    comment=wd.comment,
                    canceled=wd.canceled,
                    need_count_wh=True,
                    is_blocked=wd.is_blocked,
                    closest_plan_approved_id=wd.closest_plan_approved_id,
                    parent_worker_day_id=wd.id,
                    source=WorkerDay.SOURCE_ON_APPROVE,
                    code=wd.code,
                )
                for wd in self.to_approve_wdays if not wd.is_open_vacancy
            )
        )
        search_wds = {wd.parent_worker_day_id: wd for wd in new_draft_wdays}
        WorkerDayOutsourceNetwork.objects.bulk_create(
            (
                WorkerDayOutsourceNetwork(
                    workerday=search_wds[wd.id],
                    network=network,
                )
                for wd in self.to_approve_wdays if not wd.is_open_vacancy
                for network in wd.outsources.all()
            )
        )

        WorkerDayCashboxDetails.objects.bulk_create(
            (
                WorkerDayCashboxDetails(
                    work_part=details.work_part,
                    worker_day=search_wds[wd.id],
                    work_type_id=details.work_type_id,
                )
                for wd in self.to_approve_wdays if not wd.is_open_vacancy
                for details in wd.worker_day_details.all()
            )
        )

    def _recalc_timesheet(self):
        recalc_timesheet_on_data_change(self.employee_days_dict)

    def _delete_cache(self):
        # TODO: research how this works
        transaction.on_commit(
            lambda: [
                cache.delete_pattern(f"prod_cal_*_*_{employee_id}")
                for employee_id in self.employee_ids_for_approval
            ]
        )


    # Events
    def _post_approve_events(self):
        """Send event_signals (notifications)"""
        self._event_approve()
        if not self.is_fact:
            self._event_vacancies_created()

    def _event_approve(self):
        approve_event_context = {
            'is_fact': self.is_fact,
            'shop_id': self.shop_id,
            'employee_ids': tuple(self.employee_ids_for_approval),
            'dt_from': self.dt_from,
            'dt_to': self.dt_to,
            'approve_open_vacs': self.approve_open_vacs,
            'wd_types': tuple(self.wd_types_ids_for_approval),
        }
        transaction.on_commit(lambda: event_signal.send(
            sender=None,
            network_id=self.user.network_id if self.user else self.shop.network_id,
            event_code=APPROVE_EVENT_TYPE,
            user_author_id=self.user.id if self.user else None,
            shop_id=self.shop_id,
            context=approve_event_context,
        ))

    def _event_vacancies_created(self):
        for wd in self.to_approve_wdays:
            if wd.is_open_vacancy:
                transaction.on_commit(lambda: notify_vacancy_created(wd, is_auto=False))


    # Helpers
    @staticmethod
    def __get_employee_days_dict(wdays: Iterable[WorkerDay]) -> dict[int, set[date]]:
        # { 3456: { date(2023,1,1), date(2023,1,2) } }
        assert wdays                    # calling this without days will lead to unwanted consequences
        _dict = {}
        for wd in wdays:
            _dict.setdefault(wd.employee_id, set()).add(wd.dt)
        return _dict

    @staticmethod
    def __get_employee_days_q(employee_days_dict: dict[int, set[date]]) -> Q:
        # employee_id=1, dt__in=(date(2023,1,1)) OR employee_id=2, dt__in=(date(2023,1,1), date(2023,1,2)) OR ...
        assert employee_days_dict       # calling this with empty dict will lead to unwanted consequences
        q = Q()
        for employee_id, dates in employee_days_dict.items():
            q |= Q(employee_id=employee_id, dt__in=dates)
        return q

    @staticmethod
    def __models_to_dict(
            models: Iterable[Model],
            values: Iterable[str]
            ) -> Iterator[dict]:
        return (
            {key: getattr(model, key) for key in values}
            for model in models
        )

    def __day_key(self, worker_day: WorkerDay) -> tuple:
        """Dict key for comparing same employee days (e.g. between draft and approved)"""
        return tuple(getattr(worker_day, field) for field in self.COMPARISON_FIELDS)
