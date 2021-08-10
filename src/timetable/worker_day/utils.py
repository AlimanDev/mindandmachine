import datetime
import json

from django.conf import settings
from django.contrib.postgres.aggregates import StringAgg
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q, F, Value, CharField
from django.db.models.functions import Concat, Cast
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError, PermissionDenied

from src.base.models import (
    Employment,
    Group,
)
from src.timetable.models import (
    AttendanceRecords,
    WorkerDay,
    WorkerDayCashboxDetails,
)


def exchange(data, error_messages):
    new_wds = []
    def create_worker_day(wd_target, wd_source):
        employment = wd_target.employment
        if (wd_source.type == WorkerDay.TYPE_WORKDAY and employment is None):
            employment = Employment.objects.get_active_empl_by_priority(
                network_id=wd_source.worker.network_id, employee_id=wd_target.employee_id,
                dt=wd_source.dt,
                priority_shop_id=wd_source.shop_id,
            ).select_related(
                'position__breaks',
            ).first()
        wd_new = WorkerDay(
            type=wd_source.type,
            dttm_work_start=wd_source.dttm_work_start,
            dttm_work_end=wd_source.dttm_work_end,
            employee_id=wd_target.employee_id,
            employment=employment if wd_source.employment_id else None,
            dt=wd_target.dt,
            created_by=data['user'],
            is_approved=data['is_approved'],
            is_vacancy=wd_source.is_vacancy,
            shop_id=wd_source.shop_id,
        )
        wd_new.save()
        new_wds.append(wd_new)
        WorkerDayCashboxDetails.objects.bulk_create([
            WorkerDayCashboxDetails(
                worker_day_id=wd_new.id,
                work_type_id=wd_cashbox_details_parent.work_type_id,
                work_part=wd_cashbox_details_parent.work_part,
            )
            for wd_cashbox_details_parent in wd_source.worker_day_details.all()
        ])

    days = len(data['dates'])
    with transaction.atomic():
        wd_list = list(WorkerDay.objects.filter(
            employee_id__in=(data['employee1_id'], data['employee2_id']),
            dt__in=data['dates'],
            is_approved=data['is_approved'],
            is_fact=False,
        ).prefetch_related(
            'worker_day_details__work_type__work_type_name',
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
            id__in=data['user'].get_group_ids(day_pairs[0][0].shop),
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
            from src.celery.tasks import send_doctors_schedule_to_mis

            # если смотреть по аналогии с подтверждением, то wd_target - подтв. версия wd_source - неподтв.
            def append_mis_data(mis_data, wd_target, wd_source):
                action = None
                if wd_target.type == WorkerDay.TYPE_WORKDAY or wd_source.type == WorkerDay.TYPE_WORKDAY:
                    wd_target_has_doctor_work_type = any(
                        wd_detail.work_type.work_type_name.code == 'doctor' for wd_detail in
                        wd_target.worker_day_details.all())
                    wd_source_has_doctor_work_type = any(
                        wd_detail.work_type.work_type_name.code == 'doctor' for wd_detail in
                        wd_source.worker_day_details.all())
                    if wd_target.type != WorkerDay.TYPE_WORKDAY and wd_source.type == WorkerDay.TYPE_WORKDAY and wd_source_has_doctor_work_type:
                        action = 'create'
                    elif wd_target.type == WorkerDay.TYPE_WORKDAY and wd_source.type != WorkerDay.TYPE_WORKDAY and wd_target_has_doctor_work_type:
                        action = 'delete'
                    elif wd_source.type == wd_target.type:
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

        WorkerDay.objects_with_excluded.filter(
            employee_id__in=(data['employee1_id'], data['employee2_id']),
            dt__in=data['dates'],
            is_approved=data['is_approved'],
            is_fact=False,
        ).delete()

        for day_pair in day_pairs:
            create_worker_day(day_pair[0], day_pair[1])
            create_worker_day(day_pair[1], day_pair[0])
    return new_wds


def copy_as_excel_cells(main_worker_days, to_employee_id, to_dates, created_by=None):
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
        employee_id=to_employee_id,
        dt__in=to_dates,
        is_approved=False,
        is_fact=False,
    )
    trainee_worker_days.delete()

    created_wds = []
    wdcds_list_to_create = []
    length_main_wds = len(main_worker_days)
    for i, dt in enumerate(to_dates):
        i = i % length_main_wds
        blank_day = main_worker_days[i]

        worker_active_empl = Employment.objects.get_active_empl_by_priority(
            network_id=blank_day.employee.user.network_id, employee_id=to_employee_id,
            dt=dt,
            priority_shop_id=blank_day.shop_id,
        ).select_related(
            'position__breaks',
        ).first()

        # не создавать день, если нету активного трудоустройства на эту дату
        if not worker_active_empl:
            raise ValidationError(
                _('It is not possible to create days on the selected dates. '
                'Please check whether the employee has active employment.')
            )
        dt_to = dt
        if blank_day.dttm_work_end and blank_day.dttm_work_start and blank_day.dttm_work_end.date() > blank_day.dttm_work_start.date():
            dt_to = dt + datetime.timedelta(days=1)

        new_wd = WorkerDay.objects.create(
            employee_id=worker_active_empl.employee_id,
            employment=worker_active_empl,
            dt=dt,
            shop=blank_day.shop,
            type=blank_day.type,
            dttm_work_start=datetime.datetime.combine(
                dt, blank_day.dttm_work_start.timetz()) if blank_day.dttm_work_start else None,
            dttm_work_end=datetime.datetime.combine(
                dt_to, blank_day.dttm_work_end.timetz()) if blank_day.dttm_work_end else None,
            is_approved=False,
            is_fact=False,
            created_by_id=created_by,
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

    return created_wds, work_types


def create_fact_from_attendance_records(dt_from=None, dt_to=None, shop_ids=None, employee_days_list=None):
    assert (dt_from and dt_to) or employee_days_list
    if employee_days_list is not None:
        q = Q()
        employee_days_q = Q()
        for employee_id, days in employee_days_list:
            # добавляем соседнюю даты из будущего,
            # т.к. отметка может относиться к соседней дате (при ночных сменах, например)
            extended_dates = list(days)
            for day in days:
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
    att_records = AttendanceRecords.objects.filter(q).order_by('user_id', 'dttm')

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
            record.type = None  # проставляем None для всех, т.к. пользователь тоже мог ошибиться, TODO: проверить + тесты
            if record.terminal:
                record.employee_id = None
            record.save()


def create_worker_days_range(dates, type=WorkerDay.TYPE_WORKDAY, shop_id=None, employee_id=None, tm_work_start=None, tm_work_end=None, work_type_id=None, is_approved=False, is_vacancy=False, outsources=[], created_by=None):
    with transaction.atomic():
        created_wds = []
        employment = None
        if employee_id:
            WorkerDay.objects.filter(
                dt__in=dates,
                is_approved=is_approved,
                is_fact=False,
                employee_id=employee_id,
            ).delete()
        if employee_id and type == WorkerDay.TYPE_WORKDAY:
            employment = Employment.objects.get_active_empl_by_priority(None, dt=dates[0], priority_shop_id=shop_id, priority_work_type_id=work_type_id, employee_id=employee_id).first()
        for date in dates:
            wd = WorkerDay.objects.create(
                dt=date,
                shop_id=shop_id,
                employee_id=employee_id,
                employment=employment,
                is_vacancy=is_vacancy,
                is_approved=is_approved,
                dttm_work_start=datetime.datetime.combine(date, tm_work_start) if tm_work_start else None,
                dttm_work_end=datetime.datetime.combine(date, tm_work_end) if tm_work_end else None,
                type=type,
                is_outsource=bool(outsources),
                created_by=created_by,
                last_edited_by=created_by,
            )
            if outsources:
                wd.outsources.add(*outsources)
            if work_type_id:
                WorkerDayCashboxDetails.objects.create(
                    worker_day=wd,
                    work_type_id=work_type_id,
                )
            created_wds.append(wd)

        return created_wds
