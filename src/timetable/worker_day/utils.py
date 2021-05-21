import datetime
import json
import time

import pandas as pd
from django.conf import settings
from django.contrib.postgres.aggregates import StringAgg
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q, F, Value, CharField
from django.db.models.functions import Concat, Cast
from django.utils.translation import gettext as _
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.response import Response

from src.base.models import (
    User,
    Shop,
    Employment,
    WorkerPosition,
    Group,
    Employee,
)
from src.conf.djconfig import UPLOAD_TT_MATCH_EMPLOYMENT
from src.timetable.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    WorkType,
)
from src.timetable.utils import wd_stat_count
from src.timetable.worker_day.stat import WorkersStatsGetter
from src.timetable.worker_day.xlsx_utils.tabel import Tabel_xlsx
from src.timetable.worker_day.xlsx_utils.timetable import Timetable_xlsx
from src.util.dg.helpers import MONTH_NAMES
from src.util.download import xlsx_method
from src.util.models_converter import Converter

WORK_TYPES = {
    'в': WorkerDay.TYPE_HOLIDAY,
    'от': WorkerDay.TYPE_VACATION,
    # 'nan': WorkerDay.TYPE_HOLIDAY,
    'b': WorkerDay.TYPE_HOLIDAY,
}

SKIP_SYMBOLS = ['nan', '']

def upload_timetable_util(form, timetable_file, is_fact=False):
    """
    Принимает от клиента экселевский файл и создает расписание (на месяц)
    """
    shop_id = form['shop_id']
    shop = Shop.objects.get(id=shop_id)

    try:
        df = pd.read_excel(timetable_file)
    except KeyError:
        raise ValidationError(_('Failed to open active sheet.'))
    ######################### сюда писать логику чтения из экселя ######################################################

    users = []

    users_df = df[df.columns[:3]]
    groups = {
        f.name.lower(): f
        for f in Group.objects.all()
    }
    positions = {
        p.name.lower(): p
        for p in WorkerPosition.objects.all()
    }
    number_column = df.columns[0]
    name_column = df.columns[1]
    position_column = df.columns[2]
    users_df[number_column] = users_df[number_column].astype(str)
    users_df[name_column] = users_df[name_column].astype(str)
    users_df[position_column] = users_df[position_column].astype(str)
    error_users = []

    for index, data in users_df.iterrows():
        if data[number_column].startswith('*') or data[name_column].startswith('*') or data[position_column].startswith('*'):
            continue
        number_cond = data[number_column] != 'nan'
        name_cond = data[name_column] != 'nan'
        position_cond = data[position_column] != 'nan'
        if number_cond and (not position_cond or not name_cond):
            result = f"У сотрудника на строке {index} не распознаны или не указаны "
            if not number_cond:
                result += "номер "
            if not name_cond:
                result += "ФИО "
            if not position_cond:
                result += "должность "
            error_users.append(result)
            continue
        elif not position_cond:
            continue
        elif not name_cond:
            continue
        position = positions.get(data[position_column].lower().strip())
        if not position:
            # Нет такой должности {position}
            raise ValidationError(_('There is no such position {position}.').format(position=data[position_column]))
        names = data[name_column].split()
        tabel_code = str(data[number_column]).split('.')[0]
        created = False
        user_data = {
            'first_name': names[1] if len(names) > 1 else '',
            'last_name': names[0],
            'middle_name': names[2] if len(names) > 2 else None,
            'network_id': form.get('network_id'),
        }
        user = None
        if UPLOAD_TT_MATCH_EMPLOYMENT:
            employment = Employment.objects.filter(employee__tabel_code=tabel_code, shop=shop)
            if number_cond and employment.exists():
                employee = employment.first().employee  # TODO: покрыть тестами
                user = employee.user
                if user.last_name != names[0]:
                    error_users.append(f"У сотрудника на строке {index} с табельным номером {tabel_code} в системе фамилия {user.last_name}, а в файле {names[0]}.") #Change error
                    continue
                user.first_name = names[1] if len(names) > 1 else ''
                user.last_name = names[0]
                user.middle_name = names[2] if len(names) > 2 else None
                user.save()
            else:
                employment = Employment.objects.filter(
                    shop=shop,
                    employee__user__first_name=names[1] if len(names) > 1 else '',
                    employee__user__last_name=names[0],
                    employee__user__middle_name=names[2] if len(names) > 2 else None
                )
                if employment.exists():
                    if number_cond:
                        employment.update(tabel_code=tabel_code,)
                    employee = employment.first().employee
                else:
                    user_data['username'] = str(time.time() * 1000000)[:-2],
                    user = User.objects.create(**user_data)
                    employee = Employee.objects.create(user=user, tabel_code=tabel_code)
                    created = True
        else:
            employees_qs = Employee.objects.filter(tabel_code=tabel_code)
            if number_cond and employees_qs.exists():
                User.objects.filter(employees__in=employees_qs).update(**user_data)
                employee = employees_qs.first()
            else:
                employee = Employee.objects.filter(
                    **{'user__' + k: v for k,v in user_data.items()}
                )
                if employee.exists():
                    if number_cond:
                        employee.update(tabel_code=tabel_code,)
                    employee = employee.first()
                else:
                    user_data['username'] = str(time.time() * 1000000)[:-2]
                    if number_cond:
                        user_data['tabel_code'] = tabel_code
                    user = User.objects.create(**user_data)
                    employee = Employee.objects.create(user=user, tabel_code=tabel_code)
                    created = True
        func_group = groups.get(data[position_column].lower().strip(), groups['сотрудник'])
        if created:
            employee.user.username = f'u{user.id}'
            employee.user.save()
            employment = Employment.objects.create(
                shop_id=shop_id,
                employee=employee,
                function_group=func_group,
                position=position,
            )
            if UPLOAD_TT_MATCH_EMPLOYMENT and number_cond:
                employment.tabel_code = tabel_code
                employment.save()
        else:
            employment = Employment.objects.get_active(
                network_id=user.network_id,
                employee=employee,
            ).first()
            if not employment:
                employment = Employment.objects.create(
                    shop_id=shop_id,
                    employee=employee,
                    position=position,
                    function_group=func_group,
                )
            else:
                employment.position = position
                employment.save()
        users.append([
            employee,
            employment,
        ])
    if len(error_users):
        return Response({"message": '\n'.join(error_users)}, status=400)
    dates = []
    for dt in df.columns[3:]:
        if not isinstance(dt, datetime.datetime):
            break
        dates.append(dt.date())
    if not len(dates):
        return Response()

    work_types = {
        w.work_type_name.name.lower(): w
        for w in WorkType.objects.select_related('work_type_name').filter(shop_id=shop_id, dttm_deleted__isnull=True)
    }
    if (len(work_types) == 0):
        raise ValidationError(_('There are no active work types in this shop.'))

    first_type = next(iter(work_types.values()))
    timetable_df = df[df.columns[:3 + len(dates)]]

    timetable_df[number_column] = timetable_df[number_column].astype(str)
    timetable_df[name_column] = timetable_df[name_column].astype(str)
    timetable_df[position_column] = timetable_df[position_column].astype(str)
    index_shift = 0

    for index, data in timetable_df.iterrows():
        if data[number_column].startswith('*') or data[name_column].startswith('*') \
            or data[position_column].startswith('*'):
            index_shift += 1
            continue
        number_cond = data[number_column] != 'nan'
        name_cond = data[name_column] != 'nan'
        position_cond = data[position_column] != 'nan'
        if not number_cond and (not name_cond or not position_cond):
            index_shift += 1
            continue
        employee, employment = users[index - index_shift]
        for i, dt in enumerate(dates):
            dttm_work_start = None
            dttm_work_end = None
            try:
                cell_data = str(data[i + 3]).lower().strip()
                if cell_data.replace(' ', '').replace('\n', '') in SKIP_SYMBOLS:
                    continue
                if not (cell_data in WORK_TYPES):
                    splited_cell = data[i + 3].replace('\n', '').strip().split()
                    work_type = work_types.get(data[position_column].lower(), first_type) if len(splited_cell) == 1 else work_types.get(splited_cell[1].lower(), first_type)
                    times = splited_cell[0].split('-')
                    type_of_work = WorkerDay.TYPE_WORKDAY
                    dttm_work_start = datetime.datetime.combine(
                        dt, Converter.parse_time(times[0] + ':00')
                    )
                    dttm_work_end = datetime.datetime.combine(
                        dt, Converter.parse_time(times[1] + ':00')
                    )
                    if dttm_work_end < dttm_work_start:
                        dttm_work_end += datetime.timedelta(days=1)
                elif not is_fact:
                    type_of_work = WORK_TYPES[cell_data]
                else:
                    continue
            except:
                raise ValidationError(_('The employee {user.first_name} {user.last_name} in the cell for {dt} has the wrong value: {value}.').format(user=employee.user, dt=dt, value=str(data[i + 3])))

            WorkerDay.objects.filter(dt=dt, employee=employee, is_fact=is_fact, is_approved=False).delete()
          
            new_wd = WorkerDay.objects.create(
                employee=employee,
                shop_id=shop_id,
                dt=dt,
                is_fact=is_fact,
                is_approved=False,
                employment=employment,
                dttm_work_start=dttm_work_start,
                dttm_work_end=dttm_work_end,
                type=type_of_work,
            )
            if type_of_work == WorkerDay.TYPE_WORKDAY:
                WorkerDayCashboxDetails.objects.create(
                    worker_day=new_wd,
                    work_type=work_type,
                )

    return Response()

@xlsx_method
def download_timetable_util(request, workbook, form):
    ws = workbook.add_worksheet('Расписание на подпись')

    shop = Shop.objects.get(pk=form['shop_id'])
    timetable = Timetable_xlsx(
        workbook,
        shop,
        form['dt_from'],
        worksheet=ws,
        prod_days=None
    )

    employments = Employment.objects.get_active(
        network_id=shop.network_id,
        dt_from=timetable.prod_days[0].dt,
        dt_to=timetable.prod_days[-1].dt,
        shop=shop,
    ).select_related(
        'employee', 
        'employee__user', 
        'position',
    ).order_by('employee__user__last_name', 'employee__user__first_name', 'employee__user__middle_name', 'employee_id')
    employee_ids = employments.values_list('employee_id', flat=True)
    stat = WorkersStatsGetter(
        dt_from=timetable.prod_days[0].dt,
        dt_to=timetable.prod_days[-1].dt,
        shop_id=shop.id,
        employee_id__in=employee_ids,
    ).run()
    stat_type = 'approved' if form['is_approved'] else 'not_approved'

    workdays = WorkerDay.objects.select_related('employee', 'employee__user', 'shop').filter(
        Q(dt__lte=F('employment__dt_fired')) | Q(employment__dt_fired__isnull=True) | Q(employment__isnull=True),
        (Q(dt__gte=F('employment__dt_hired')) | Q(employment__isnull=True)) & Q(dt__gte=timetable.prod_days[0].dt),
        employee_id__in=employee_ids,
        dt__lte=timetable.prod_days[-1].dt,
        is_approved=form['is_approved'],
        is_fact=False,
    ).order_by(
        'employee__user__last_name', 'employee__user__first_name', 'employee__user__middle_name', 'employee_id', 'dt')

    workdays = workdays.get_last_ordered(
        is_fact=False,
        order_by=[
            '-is_approved' if form['is_approved'] else 'is_approved',
            '-is_vacancy',
            '-id',
        ]
    )

    if form.get('inspection_version', False):
        timetable.change_for_inspection(timetable.prod_month.get('norm_work_hours', 0), workdays)

    timetable.format_cells(len(employments))

    # construct weekday
    timetable.construct_dates('%w', 8, 4)

    # construct day 2
    timetable.construct_dates('%d.%m', 9, 4)
    timetable.add_main_info()

    # construct user info
    timetable.construnts_users_info(employments, 11, 0, ['code', 'fio', 'position'])

    # fill page 1
    timetable.fill_table(workdays, employments, stat, 11, 4, stat_type=stat_type)

    # fill page 2
    timetable.fill_table2(shop, timetable.prod_days[-1].dt, workdays)

    return workbook, 'Cashiers_timetable'


@xlsx_method
def download_tabel_util(request, workbook, form):
    """
    Скачать табель на дату
    Args:
        method: GET
        url: api/download/get_tabel
        shop_id(int): required = False
        weekday(QOS_DATE): на какую дату табель хотим
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)
    Returns:
        Табель
    """
    ws = workbook.add_worksheet(MONTH_NAMES[form['dt_from'].month])

    shop = Shop.objects.get(pk=form['shop_id'])

    tabel = Tabel_xlsx(
        workbook,
        shop,
        form['dt_from'],
        worksheet=ws,
        prod_days=None
    )

    from_dt = tabel.prod_days[0].dt
    to_dt = tabel.prod_days[-1].dt

    employments = Employment.objects.get_active(
        network_id=shop.network_id,
        dt_from=from_dt,
        dt_to=to_dt,
        shop=shop,
    ).select_related('position').order_by('position_id', 'user__last_name', 'user__first_name', 'tabel_code', 'id')

    workdays = WorkerDay.objects.select_related('worker', 'shop').filter(
        Q(dt__lt=F('employment__dt_fired')) | Q(employment__dt_fired__isnull=True),
        Q(dt__gte=F('employment__dt_hired')) & Q(dt__gte=from_dt),
        employment__in=employments,
        dt__lte=to_dt,
        is_approved=form['is_approved'],
        is_fact=False,
    ).order_by('employment__position_id', 'employee__user__last_name', 'employee__user__first_name', 'employment__tabel_code', 'employment__id', 'dt')

    wd_stat = wd_stat_count(workdays, shop)
    working_hours = {}
    for wd in wd_stat:
        if wd['worker_id'] not in working_hours:
            working_hours[wd['worker_id']] = {}
        working_hours[wd['worker_id']][wd['dt']] = wd['hours_fact']

    default_breaks = list(map(lambda x: (x[0] / 60, x[1] / 60, sum(x[2]) / 60), shop.settings.breaks.breaks))
    breaktimes = {
        w.id: list(map(lambda x: (x[0] / 60, x[1] / 60, sum(x[2]) / 60), w.breaks.breaks)) if w.breaks else default_breaks
        for w in WorkerPosition.objects.filter(network_id=shop.network_id)
    }
    breaktimes['default'] = default_breaks
    # breaktimes = json.loads(shop.settings.break_triplets)
    # breaktimes = list(map(lambda x: (x[0] / 60, x[1] / 60, sum(x[2]) / 60), breaktimes))

    if form.get('inspection_version', False):
        tabel.change_for_inspection(tabel.prod_month.get('norm_work_hours', 0), workdays)

    tabel.format_cells(len(employments))
    tabel.add_main_info()

    # construct day
    tabel.construct_dates('%d', 12, 6, int)

    # construct weekday
    tabel.construct_dates('%w', 14, 6)

    # construct day 2
    tabel.construct_dates('d%d', 15, 6)

    tabel.construnts_users_info(employments, 16, 0, ['code', 'fio', 'position', 'hired'], extra_row=True)
    tabel.fill_table(workdays, employments, breaktimes, working_hours, 16, 6)
    tabel.add_xlsx_functions(len(employments), 12, 37, extra_row=True)
    tabel.add_sign(16 + len(employments) * 2 + 2)

    return workbook, 'Tabel'


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
                dates=StringAgg(Cast('dt', CharField()), delimiter=','),
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
                json_data = json.dumps(mis_data, indent=4, ensure_ascii=False, cls=DjangoJSONEncoder)
                send_doctors_schedule_to_mis.delay(json_data=json_data)

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
                'Невозможно создать дни в выбранные даты. '
                'Пожалуйста, проверьте наличие активного трудоустройства у сотрудника.'
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
