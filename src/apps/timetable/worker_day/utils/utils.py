import datetime
import json
from collections import OrderedDict

from django.conf import settings
from django.contrib.postgres.aggregates import StringAgg
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q, F, Value, CharField, Prefetch
from django.db.models.functions import Concat, Cast
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError, PermissionDenied

from src.apps.base.models import (
    Employment,
    Group,
    User, Network,
)
from src.apps.timetable.models import (
    AttendanceRecords,
    EmploymentWorkType,
    WorkerDay,
    WorkerDayCashboxDetails,
)


ERROR_MESSAGES = {
    'worker_days_mismatch': _('Worker days mismatch.'),
    'no_timetable': _("Workers don't have timetable."),
    'cannot_delete': _('Cannot_delete approved version.'),
    'na_worker_day_exists': _('Not approved version already exists.'),
    'no_action_perm_for_wd_type': _('You do not have rights to {action_str} the day type "{wd_type_str}"'),
    'no_action_perm': _('You do not have rights to {action_str}'),
    'wd_interval_restriction': _('You do not have the rights to {action_str} the type of day "{wd_type_str}" '
                                            'on the selected dates. '
                                            'You need to change the dates. '
                                            'Allowed interval: {dt_interval}'),
    'has_no_perm_to_approve_protected_wdays': _('You do not have rights to approve protected worker days ({protected_wdays}). '
                                                'Please contact your system administrator.'),
    'no_such_user_in_network': _('There is no such user in your network.'),
    'employee_not_in_subordinates': _('Employee {employee} is not your subordinate.'),
    'no_wd_types': _('No day types to {action_str}')
}


def exchange(data, error_messages):
    created_wdays = []
    def get_wd_data(wd_target, wd_source):
        employment = wd_target.employment
        if (wd_source.type_id == WorkerDay.TYPE_WORKDAY and employment is None):
            employment = Employment.objects.get_active_empl_by_priority(
                network_id=wd_source.employee.user.network_id, employee_id=wd_target.employee_id,  # TODO: тест
                dt=wd_source.dt,
                priority_shop_id=wd_source.shop_id,
            ).select_related(
                'position__breaks',
            ).first()
        main_work_type_id = None
        if len(wd_source.worker_day_details_list):
            main_work_type_id = getattr(EmploymentWorkType.objects.filter(employment_id=employment.id, priority=1)
                                        .first(), 'work_type_id', None)
        wd_data = dict(
            type_id=wd_source.type_id,
            dttm_work_start=wd_source.dttm_work_start,
            dttm_work_end=wd_source.dttm_work_end,
            employee_id=wd_target.employee_id,
            employment=employment,
            dt=wd_target.dt,
            created_by=data['user'],
            is_approved=data['is_approved'],
            shop_id=wd_source.shop_id,
            source=WorkerDay.SOURCE_EXCHANGE_APPROVED if data['is_approved'] else WorkerDay.SOURCE_EXCHANGE,
        )
        wd_data['outsources'] = [dict(network_id=network.id) for network in wd_source.outsources_list]
        wd_data['worker_day_details'] = [
            dict(
                work_type_id=wd_cashbox_details_parent.work_type_id,
                work_part=wd_cashbox_details_parent.work_part,
            )
            for wd_cashbox_details_parent in wd_source.worker_day_details_list
        ]
        wd_data['is_vacancy'] = WorkerDay.is_worker_day_vacancy(
            employment.shop_id,
            wd_data['shop_id'],
            main_work_type_id,
            wd_source.worker_day_details_list,
            is_vacancy=wd_source.is_vacancy,
        )
        return wd_data

    days = len(data['dates'])
    with transaction.atomic():
        wd_list = list(WorkerDay.objects.filter(
            employee_id__in=(data['employee1_id'], data['employee2_id']),
            dt__in=data['dates'],
            is_approved=data['is_approved'],
            is_fact=False,
        ).prefetch_related(
            Prefetch(
                'worker_day_details',
                queryset=WorkerDayCashboxDetails.objects.select_related('work_type__work_type_name'),
                to_attr='worker_day_details_list',
            ),
            Prefetch(
                'outsources',
                to_attr='outsources_list',
            ),
        ).select_related(
            'employee__user',
            'employment',
        ).order_by('dt'))

        if len(wd_list) != days * 2:
            raise ValidationError(error_messages['no_timetable'])

        day_pairs = []
        for day_ind in range(days):
            day_pair = [wd_list[day_ind * 2], wd_list[day_ind * 2 + 1]]
            if day_pair[0].dt != day_pair[1].dt:
                raise ValidationError(error_messages['worker_days_mismatch'])
            day_pairs.append(day_pair)

        # если у пользователя нет группы с наличием прав на изменение защищенных дней, то проверяем,
        # что в списке изменяемых дней нету защищенных дней, если есть, то выдаем ошибку
        has_permission_to_change_protected_wdays = Group.objects.filter(
            id__in=data['user'].get_group_ids(day_pairs[0][0].shop_id),
            has_perm_to_change_protected_wdays=True,
        ).exists()
        if not has_permission_to_change_protected_wdays:
            protected_wdays = list(WorkerDay.objects.filter(
                employee_id__in=(data['employee1_id'], data['employee2_id']),
                dt__in=data['dates'],
                is_approved=data['is_approved'],
                is_fact=False,
                is_blocked=True,
            ).annotate(
                worker_fio=Concat(
                    F('employee__user__last_name'), Value(' '),
                    F('employee__user__first_name'), Value(' ('),
                    F('employee__user__username'), Value(')'),
                ),
            ).values(
                'worker_fio',
            ).annotate(
                dates=StringAgg(Cast('dt', CharField()), delimiter=',', ordering='dt'),
            ))
            if protected_wdays:
                raise PermissionDenied(error_messages['has_no_perm_to_approve_protected_wdays'].format(
                    protected_wdays=', '.join(f'{d["worker_fio"]}: {d["dates"]}' for d in protected_wdays),
                ))

        if data['is_approved'] and settings.SEND_DOCTORS_MIS_SCHEDULE_ON_CHANGE:
            from src.adapters.celery.tasks import send_doctors_schedule_to_mis

            # если смотреть по аналогии с подтверждением, то wd_target - подтв. версия wd_source - неподтв.
            def append_mis_data(mis_data, wd_target, wd_source):
                action = None
                if wd_target.type_id == WorkerDay.TYPE_WORKDAY or wd_source.type_id == WorkerDay.TYPE_WORKDAY:
                    wd_target_has_doctor_work_type = any(
                        wd_detail.work_type.work_type_name.code == 'doctor' for wd_detail in
                        wd_target.worker_day_details_list)
                    wd_source_has_doctor_work_type = any(
                        wd_detail.work_type.work_type_name.code == 'doctor' for wd_detail in
                        wd_source.worker_day_details_list)
                    if wd_target.type_id != WorkerDay.TYPE_WORKDAY and wd_source.type_id == WorkerDay.TYPE_WORKDAY and wd_source_has_doctor_work_type:
                        action = 'create'
                    elif wd_target.type_id == WorkerDay.TYPE_WORKDAY and wd_source.type_id != WorkerDay.TYPE_WORKDAY and wd_target_has_doctor_work_type:
                        action = 'delete'
                    elif wd_source.type_id == wd_target.type_id:
                        if wd_source_has_doctor_work_type and wd_target_has_doctor_work_type:
                            action = 'update'
                        elif wd_source_has_doctor_work_type and not wd_target_has_doctor_work_type:
                            action = 'create'
                        elif wd_target_has_doctor_work_type and not wd_source_has_doctor_work_type:
                            action = 'delete'

                if action:
                    mis_data.append({
                        'dt': wd_target.dt,
                        'employee__user__username': wd_target.employee.user.username,
                        'shop__code': wd_target.shop.code if wd_target.shop else wd_source.shop.code,
                        'dttm_work_start': wd_target.dttm_work_start if action == 'delete' else wd_source.dttm_work_start,
                        'dttm_work_end': wd_target.dttm_work_end if action == 'delete' else wd_source.dttm_work_end,
                        'action': action,
                    })

            mis_data = []
            for day_pair in day_pairs:
                append_mis_data(mis_data, day_pair[0], day_pair[1])
                append_mis_data(mis_data, day_pair[1], day_pair[0])

            if mis_data:
                json_data = json.dumps(mis_data, cls=DjangoJSONEncoder)
                transaction.on_commit(
                    lambda f_json_data=json_data: send_doctors_schedule_to_mis.delay(json_data=f_json_data))

        wdays = []
        for day_pair in day_pairs:
            wdays.append(get_wd_data(day_pair[0], day_pair[1]))
            wdays.append(get_wd_data(day_pair[1], day_pair[0]))
        created_wdays, stats = WorkerDay.batch_update_or_create(data=wdays, user=data['user'])
    return created_wdays


def copy_as_excel_cells(from_employee_id, from_dates, to_employee_id, to_dates, user=None,
                              is_approved=False, worker_day_types=None, include_spaces=False):
    main_worker_days = WorkerDay.objects.filter(
        employee_id=from_employee_id,
        dt__in=from_dates,
        is_fact=False,
        is_approved=is_approved,
    ).select_related(
        'employee__user',
        'employment__shop',
        'shop__settings__breaks',
        'shop__network__breaks',
    ).prefetch_related(
        Prefetch(
            'outsources',
            to_attr='outsources_list',
        ),
    ).order_by('dt')
    source = WorkerDay.SOURCE_DUPLICATE
    if include_spaces:
        source = WorkerDay.SOURCE_COPY_RANGE
    if worker_day_types:
        main_worker_days = main_worker_days.filter(type_id__in=worker_day_types)
    main_worker_days = list(main_worker_days)
    main_worker_days_details_set = list(WorkerDayCashboxDetails.objects.filter(
        worker_day__in=main_worker_days,
    ).select_related('work_type'))

    main_worker_days_details = {}
    for detail in main_worker_days_details_set:
        main_worker_days_details.setdefault(detail.worker_day_id, []).append(detail)

    main_worker_days_grouped_by_dt = OrderedDict()
    if include_spaces:
        main_worker_days_grouped_by_dt = OrderedDict([(dt, []) for dt in from_dates])
    for main_worker_day in main_worker_days:
        key = main_worker_day.dt
        main_worker_days_grouped_by_dt.setdefault(key, []).append(main_worker_day)

    main_worker_days_lists = list(main_worker_days_grouped_by_dt.values())
    length_main_wds = len(main_worker_days_lists)

    created_wds = []
    if main_worker_days:
        new_wdays_data = []
        for i, dt in enumerate(to_dates):
            i = i % length_main_wds

            blank_days = main_worker_days_lists[i]
            if not blank_days:
                continue

            worker_active_empl = Employment.objects.get_active_empl_by_priority(
                employee_id=to_employee_id,
                dt=dt,
                priority_shop_id=blank_days[0].shop_id,
                annotate_main_work_type_id=True,
            ).select_related(
                'position__breaks',
                'employee__user',
            ).first()

            # не создавать день, если нету активного трудоустройства на эту дату
            if not worker_active_empl:
                raise ValidationError(
                    _('It is not possible to create days on the selected dates. '
                      'Please check whether the employee has active employment.')
                )

            for blank_day in blank_days:
                dt_to = dt
                if blank_day.dttm_work_end and blank_day.dttm_work_start and blank_day.dttm_work_end.date() > blank_day.dttm_work_start.date():
                    dt_to = dt + datetime.timedelta(days=1)

                wd_data = dict(
                    employee_id=worker_active_empl.employee_id,
                    employment=worker_active_empl,
                    dt=dt,
                    shop_id=blank_day.shop_id,
                    type_id=blank_day.type_id,
                    dttm_work_start=datetime.datetime.combine(
                        dt, blank_day.dttm_work_start.timetz()) if blank_day.dttm_work_start else None,
                    dttm_work_end=datetime.datetime.combine(
                        dt_to, blank_day.dttm_work_end.timetz()) if blank_day.dttm_work_end else None,
                    is_approved=False,
                    is_fact=False,
                    created_by=user,
                    last_edited_by=user,
                    source=source,
                    work_hours=blank_day.work_hours,
                )
                if blank_day.shop_id:
                    wd_data['is_outsource'] = blank_day.shop.network_id != worker_active_empl.employee.user.network_id
                    if wd_data['is_outsource']:
                        wd_data['outsources'] = [dict(network_id=network.id) for network in blank_day.outsources_list]
                new_wdcds = main_worker_days_details.get(blank_day.id, [])
                wd_data['worker_day_details'] = [
                    dict(work_type_id=new_wdcd.work_type_id, work_part=new_wdcd.work_part, ) for new_wdcd in new_wdcds]
                wd_data['is_vacancy'] = WorkerDay.is_worker_day_vacancy(
                    worker_active_empl.shop_id,
                    blank_day.shop_id,
                    worker_active_empl.main_work_type_id,
                    wd_data['worker_day_details'],
                    is_vacancy=blank_day.is_vacancy,
                )
                new_wdays_data.append(wd_data)

        created_wds, stats = WorkerDay.batch_update_or_create(
            data=new_wdays_data,
            user=user,
            check_perms_extra_kwargs=dict(
                check_active_empl=False,
                grouped_checks=True,
            )
        )

    work_types = [
        (wdcds.work_type.shop_id, wdcds.work_type_id)
        for wdcds in main_worker_days_details_set
    ]

    return created_wds, work_types


def create_fact_from_attendance_records(dt_from=None, dt_to=None, shop_ids=None, employee_days_list=None):
    assert (dt_from and dt_to) or employee_days_list
    if employee_days_list is not None:
        q = Q()
        employee_days_q = Q()
        for employee_id, days in employee_days_list:
            # добавляем соседние даты,
            # т.к. отметка может относиться к соседней дате (при ночных сменах, например)
            extended_dates = list(days)
            for day in days:
                prev_dt = day - datetime.timedelta(days=1)
                if prev_dt not in extended_dates:
                    extended_dates.append(prev_dt)
                next_dt = day + datetime.timedelta(days=1)
                if next_dt not in extended_dates:
                    extended_dates.append(next_dt)

            employee_days_q |= Q(employee_id=employee_id, dt__in=extended_dates)
        q &= employee_days_q
    else:
        q = Q(
            dt__gte=dt_from,
            dt__lte=dt_to + datetime.timedelta(1),
        )
        if shop_ids:
            q &= Q(shop_id__in=shop_ids)
    att_records = AttendanceRecords.objects.filter(q).select_related(
        'shop',
        'user__network',
    ).order_by(
        'user_id',
        'dttm'
    )

    with transaction.atomic():
        wds_q = Q(
            last_edited_by__isnull=True,  # TODO: тест, что ручные изменения не удаляются
            is_fact=True,
            shop_id__in=att_records.values_list('shop_id', flat=True),  # TODO: правильно?
        )
        if employee_days_list is not None:
            wds_q &= employee_days_q
        else:
            wds_q &= Q(
                dt__gte=dt_from,
                dt__lte=dt_to + datetime.timedelta(1),
            )
            if shop_ids:
                q &= Q(shop_id__in=shop_ids)

        # удаляем факт не созданный вручную
        WorkerDay.objects.filter(wds_q).delete()

        for record in att_records:
            if record.terminal:
                record.type = None
                record.employee_id = None
            record.save(recalc_fact_from_att_records=True)


def create_worker_days_range(dates, type_id=WorkerDay.TYPE_WORKDAY, shop_id=None, employee_id=None, tm_work_start=None, tm_work_end=None, cashbox_details=[], is_approved=False, is_vacancy=False, outsources=[], created_by=None):
    with transaction.atomic():
        created_wds = []
        employment = None
        priority_work_type_id = None
        if cashbox_details:
            priority_work_type_id = sorted(cashbox_details, key=lambda x: x['work_part'])[0]['work_type_id']
        wdays = []
        for date in dates:
            if employee_id:
                employment = Employment.objects.get_active_empl_by_priority(
                    network_id=None,
                    employee_id=employee_id,
                    dt=date,
                    priority_shop_id=shop_id,
                    priority_work_type_id=priority_work_type_id,
                    annotate_main_work_type_id=True,
                ).select_related(
                    'position__breaks',
                ).first()

                # не создавать день, если нету активного трудоустройства на эту дату
                if not employment:
                    raise ValidationError(
                        _('It is not possible to create days on the selected dates. '
                        'Please check whether the employee has active employment.')
                    )
            dt_to = date
            if tm_work_start and tm_work_end and tm_work_end < tm_work_start:
                dt_to = date + datetime.timedelta(days=1)
            wd_data = dict(
                dt=date,
                shop_id=shop_id,
                employee_id=employee_id,
                employment_id=employment.id if employment else None,
                is_approved=is_approved,
                dttm_work_start=datetime.datetime.combine(date, tm_work_start) if tm_work_start else None,
                dttm_work_end=datetime.datetime.combine(dt_to, tm_work_end) if tm_work_end else None,
                type_id=type_id,
                is_outsource=bool(outsources),
                created_by=created_by,
                last_edited_by=created_by,
                source=WorkerDay.SOURCE_CHANGE_LIST,
            )
            if type_id == WorkerDay.TYPE_WORKDAY:
                if outsources and is_vacancy:
                    wd_data['outsources'] = [dict(network_id=network.id) for network in outsources]
                wd_data['worker_day_details'] = [dict(work_type_id=detail['work_type_id'], work_part=detail['work_part']) for detail in cashbox_details]
            wd_data['is_vacancy'] = WorkerDay.is_worker_day_vacancy(
                getattr(employment, 'shop_id', None),
                shop_id,
                getattr(employment, 'main_work_type_id', None),
                [{'work_type_id': priority_work_type_id}] if priority_work_type_id else [],
                is_vacancy=is_vacancy,
            )
            wdays.append(wd_data)

        if wdays:
            created_wds, _stats = WorkerDay.batch_update_or_create(
                data=wdays, user=created_by,
                check_perms_extra_kwargs=dict(
                    check_active_empl=False,  # проверка наличия трудоустройства происходит выше
                    grouped_checks=True,
                ),
                delete_scope_filters={'employee__isnull': False},  # не удаляем открытые вакансии при создании новых
            )

        return created_wds


def can_edit_worker_day(wd: WorkerDay, user: User) -> bool:
    day_is_blocked: bool = wd.is_blocked
    has_perm_to_change_protected_wdays: bool = Group.objects.filter(
        id__in=user.get_group_ids(),
        has_perm_to_change_protected_wdays=True,
    ).exists()
    if day_is_blocked and not has_perm_to_change_protected_wdays:
        return False
    day_is_from_integration: bool = bool(wd.code)  # from 1c if code is present
    network: Network = user.network
    if day_is_from_integration and network:
        forbid_edit_integration_wd: bool = network.forbid_edit_work_days_came_through_integration
        if forbid_edit_integration_wd and not has_perm_to_change_protected_wdays:
            return False
    return True


def time_is_in_range(time, time_range) -> bool:
    if time_range[0] <= time_range[1]:
        return time_range[0] <= time <= time_range[1]
    else:
        return time_range[0] <= time or time <= time_range[1]


def time_intersection(datetime_range: (datetime, datetime), time_range: (datetime.time, datetime.time)) -> \
        (datetime.time, datetime.time) or None:
    """Finds an intersection between datetime range and time(usually night hours) range"""
    start_date = datetime_range[0].date()
    end_date = datetime_range[1].date()
    check_double = False
    if time_is_in_range(datetime_range[0].time(), time_range):
        end_time_in_range = time_is_in_range(datetime_range[1].time(), time_range)
        if not end_time_in_range:
            second_boundary = time_range[1]
        else:
            second_boundary = min(datetime_range[1].time(), time_range[1]) if end_date > start_date \
            else datetime_range[1].time()
        inter = datetime_range[0].time(), second_boundary
        if datetime_range[1].time() > time_range[0] != datetime_range[0].time():
            check_double = True
    elif time_is_in_range(datetime_range[1].time(), time_range):
        inter = max(datetime_range[0].time(), time_range[0]), datetime_range[1].time()
    elif end_date > start_date:
       inter = time_range
    else:
        inter = None
    if check_double:
        first_boundary = datetime_range[1].replace(hour=time_range[0].hour, minute=time_range[0].minute)
        second_boundary = datetime_range[1]
        second_inter = time_intersection([first_boundary, second_boundary], time_range)
        inter = inter[0], inter[1].replace(hour=time_range[1].hour, minute=time_range[1].minute)
        return inter, second_inter
    inter = inter if inter and not inter[0] == inter[1] else None
    return inter

# def check_worker_day_permissions(user, shop_id, action, graph_type, wd_types, dt_from, dt_to, error_messages, wd_types_dict, employee_id=None, is_vacancy=False):
#     user_shops = list(user.get_shops(include_descendants=True).values_list('id', flat=True))
#     get_subordinated_group_ids = Group.get_subordinated_group_ids(user)
#     for dt in pd.date_range(dt_from, dt_to).date:
#         if not WorkerDay._has_group_permissions(
#                 user, employee_id, dt,
#                 user_shops=user_shops, get_subordinated_group_ids=get_subordinated_group_ids, shop_id=shop_id, is_vacancy=is_vacancy,
#         ):
#             raise PermissionDenied(
#                 error_messages['employee_not_in_subordinates'].format(
#                 employee=User.objects.filter(employees__id=employee_id).first().fio),
#             )

#     wd_perms = GroupWorkerDayPermission.objects.filter(
#         group__in=user.get_group_ids(shop_id=shop_id),
#         worker_day_permission__action=action,
#         worker_day_permission__graph_type=graph_type,
#     ).select_related('worker_day_permission').values_list(
#         'worker_day_permission__wd_type_id', 'limit_days_in_past', 'limit_days_in_future', 'employee_type', 'shop_type',
#     ).distinct()
#     wd_perms_dict = {wdp[0]: wdp for wdp in wd_perms}

#     today = (datetime.datetime.now() + datetime.timedelta(hours=3)).date()
#     for wd_type_id in wd_types:
#         wdp = wd_perms_dict.get(wd_type_id)
#         wd_type_obj = wd_types_dict.get(wd_type_id)
#         if not wd_type_obj:
#             raise PermissionDenied(
#                 f'There are no day type with code={wd_type_id}'
#             )
#         wd_type_display_str = wd_type_obj.name
#         if wdp is None:
#             raise PermissionDenied(
#                 error_messages['no_action_perm_for_wd_type'].format(
#                     wd_type_str=wd_type_display_str,
#                     action_str=WorkerDayPermission.ACTIONS_DICT.get(action).lower()),
#             )

#         limit_days_in_past = wdp[1]
#         limit_days_in_future = wdp[2]
#         date_limit_in_past = None
#         date_limit_in_future = None
#         if limit_days_in_past is not None:
#             date_limit_in_past = today - datetime.timedelta(days=limit_days_in_past)
#         if limit_days_in_future is not None:
#             date_limit_in_future = today + datetime.timedelta(days=limit_days_in_future)
#         if date_limit_in_past or date_limit_in_future:
#             if (date_limit_in_past and dt_from < date_limit_in_past) or \
#                     (date_limit_in_future and dt_to > date_limit_in_future):
#                 dt_interval = f'с {Converter.convert_date(date_limit_in_past) or "..."} ' \
#                                 f'по {Converter.convert_date(date_limit_in_future) or "..."}'
#                 raise PermissionDenied(
#                     error_messages['wd_interval_restriction'].format(
#                         wd_type_str=wd_type_display_str,
#                         action_str=WorkerDayPermission.ACTIONS_DICT.get(action).lower(),
#                         dt_interval=dt_interval,
#                     )
#                 )
#     return wd_perms
