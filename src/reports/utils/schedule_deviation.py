from datetime import date
from collections import OrderedDict
from functools import reduce
import io
import pandas as pd
import xlrd
from django.db.models import (
    Q, 
    OuterRef, 
    Subquery, 
    CharField, 
    F, 
    FloatField, 
    Value, 
    IntegerField, 
    ExpressionWrapper,
    BooleanField,
)
from django.db.models.functions import Coalesce, Extract, Cast, Concat
import xlsxwriter

from src.base.models import Employment, Shop, User

from src.timetable.models import (
    ScheduleDeviations, 
    WorkerDay, 
    WorkerDayCashboxDetails, 
    WorkerDayOutsourceNetwork,
    WorkerDayType,
)

def_style = {
    'border': 1,
    'valign': 'vcenter',
    'align': 'center',
    'text_wrap': True,
}
header_style = {
    'border': 1,
    'bold': True,
    'text_wrap': True,
    'valign': 'vcenter',
    'align': 'center',
    'bg_color': '#d9d9d9',
}
date_style = {
    'border': 1,
    'valign': 'vcenter',
    'align': 'center',
    'text_wrap': True,
    'num_format': 'dd.mm.yyyy',
}

columns_df = [
    'dt',
    'shop_name',
    'worker_fio',
    'tabel_code',
    'user_network',
    'is_outsource',
    'work_type_name',
    'plan_work_hours',
    'fact_work_hours',
    'fact_manual_work_hours',
    'late_arrival_hours',
    'late_arrival_count',
    'early_arrival_hours',
    'early_arrival_count',
    'early_departure_hours',
    'early_departure_count',
    'late_departure_hours',
    'late_departure_count',
    'fact_without_plan_work_hours',
    'lost_work_hours',
    'lost_work_hours_count',
    'wd_type_id',
    'employment_shop_name',
    'position_name',
    'dttm_work_start_fact',
    'dttm_work_end_fact',
]
values_df = columns_df.copy()


table_columns = [
    {'col_name': 'number', 'col_title': '№', 'col_width': 4, 'type': int},
    {'col_name': 'region', 'col_title': 'Регион', 'col_width': 25, 'type': str, 'is_extra': True},
    {'col_name': 'region_manager', 'col_title': 'РР', 'col_width': 25, 'type': str, 'is_extra': True},
    {'col_name': 'supervisor_mentor', 'col_title': 'СВН', 'col_width': 25, 'type': str, 'is_extra': True},
    {'col_name': 'supervisor', 'col_title': 'СВ', 'col_width': 25, 'type': str, 'is_extra': True},
    {'col_name': 'shop', 'col_title': 'Магазин\объект', 'type': str, 'col_width': 36},
    {'col_name': 'date', 'col_title': 'Дата', 'type': 'date', 'col_width': 20},
    {'col_name': 'worker_fio', 'col_title': 'ФИО сотрудника', 'type': str, 'col_width': 33 },
    {'col_name': 'tabel_code', 'col_title': 'Табельный номер', 'type': int, 'col_width': 22},
    {'col_name': 'network_shop', 'col_title': 'Закрепленная компания/магазин', 'type': str, 'col_width': 36},
    {'col_name': 'is_outsource', 'col_title': 'Штат или нет', 'type': str, 'col_width': 14},
    {'col_name': 'work_type', 'col_title': 'Должность/вид работ', 'type': str, 'col_width': 18},
    {'col_name': 'worker_day_type', 'col_title': 'Тип дня', 'type': str, 'col_width': 18},
    {'col_name': 'plan_work_hours', 'col_title': 'План', 'type': int, 'col_width': 9},
    {'col_name': 'fact_work_hours', 'col_title': 'Факт', 'type': int, 'col_width': 9},
    {'col_name': 'manual_hours', 'col_title': 'Скорректировано вручную', 'type': int, 'col_width': 18},
    {'col_name': 'late_arrival_hours', 'col_title': 'Опоздание часы', 'type': int, 'col_width': 13},
    {'col_name': 'late_arrival_count', 'col_title': 'Опоздания кол-во раз', 'type': int, 'col_width': 11},
    {'col_name': 'early_arrival_hours', 'col_title': 'Ранний приход на работу часы', 'type': int, 'col_width': 13},
    {'col_name': 'early_arrival_count', 'col_title': 'Ранний приход на работу количество раз', 'type': int, 'col_width': 14},
    {'col_name': 'early_departure_hours', 'col_title': 'Ранний уход часы', 'type': int, 'col_width': 13},
    {'col_name': 'early_departure_count', 'col_title': 'Ранний уход с работы количество раз', 'type': int, 'col_width': 13},
    {'col_name': 'late_departure_hours', 'col_title': 'Поздний уход с работы часы', 'type': int, 'col_width': 13},
    {'col_name': 'late_departure_count', 'col_title': 'Поздний уход с работы_количество раз', 'type': int, 'col_width': 14},
    {'col_name': 'lost_hours', 'col_title': 'Потерянное время часы', 'type': int, 'col_width': 14},
    {'col_name': 'lost_count', 'col_title': 'Потерянное время количество раз', 'type': int, 'col_width': 17},
    {'col_name': 'unplanned_work_shifts_one_tick_count', 'col_title': 'Выходы вне плана с одной отметкой, кол-во раз', 'type': int, 'col_width': 13, 'is_extra': True},
    {'col_name': 'unplanned_work_shifts_hours', 'col_title': 'Выходы вне плана с двумя отметками, часы', 'type': int, 'col_width': 13, 'is_extra': True},
    {'col_name': 'unplanned_work_shifts_count', 'col_title': 'Выходы вне плана с двумя отметками, кол-во раз', 'type': int, 'col_width': 13, 'is_extra': True},
]

def _remove_duplicate_days(output):
    """If there are duplicates where one day is a work day, and another is a non-work day,
    leave only non-work day with all the data from work day"""
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    writer.save()
    output.seek(0)
    book = xlrd.open_workbook(file_contents=output.read())
    df = pd.read_excel(book, header=10)
    work_dups = df[df.duplicated(['Дата', 'ФИО сотрудника', 'Должность/вид работ', 'Закрепленная компания/магазин'])]
    non_work_dups = df.iloc[list(work_dups.index - 1)]["Тип дня"]
    non_work_dups.index = non_work_dups.index + 1
    work_dups["Тип дня"] = non_work_dups
    df.drop(list(non_work_dups.index - 1), inplace=True)
    df.reset_index(inplace=True, drop=True)
    df["№"] = df.index + 1


def _write_header(worksheet, dt_from, dt_to, shop_object, user_created_fio):
    worksheet.write_string(1, 1, 'Наименование')
    worksheet.write_string(1, 2, '"Отчет по отклонениям от планового графика"')
    worksheet.write_string(3, 1, 'Период анализа:')
    worksheet.write_string(3, 2, f'(от): {dt_from.strftime("%d.%m.%Y")}')
    worksheet.write_string(3, 3, f'(до): {dt_to.strftime("%d.%m.%Y")}')
    worksheet.write_string(5, 1, 'Объект:')
    worksheet.write_string(5, 2, shop_object)
    worksheet.write_string(7, 1, 'Данные о формировании отчета:')
    worksheet.write_string(8, 1, f'(дата): {date.today().strftime("%d.%m.%Y")}')
    worksheet.write_string(8, 2, '(пользователь):')
    worksheet.write_string(8, 3, user_created_fio)


def _stylize_sheet(worksheet, columns, header_format, include_extra_columns=False):
    start_row = 10
    for col in table_columns:
        if not include_extra_columns and col.get('is_extra'):
            continue
        worksheet.write_string(start_row, columns[col['col_name']], col['col_title'], header_format)
        worksheet.set_column(columns[col['col_name']], columns[col['col_name']], col['col_width'])



def __calc_day_work_hours(row, work_days):
    """fact_without_plan won't show true value if network setting only_fact_hours_that_in_approved_plan is True
    to get correct value we need to calculate it manually"""
    override_skip = False
    last_name = row.worker_fio.split(' ')[0]
    kwargs = {
        'dt': row["dt"].date(), 'shop__name': row["shop_name"],
         'employee__user__last_name': last_name, 'type': WorkerDay.TYPE_WORKDAY,
        }
    work_shifts = [w for w in work_days if all(item in w.items() for item in kwargs.items())]
    work_shifts_fact = [x for x in work_shifts if x['is_fact']]
    work_shifts_plan = [x for x in work_shifts if not x['is_fact']]
    planned_dates = [x['dt'] for x in work_shifts_plan]
    unplanned_work_shifts_count = 0
    unplanned_work_shifts_one_tick_count = 0
    unplanned_work_shifts_hours = 0
    delta_work_hours_plan = delta_work_hours_fact= 0
    if len(work_shifts_fact) > 1:
        hours_fact = 0
        for shift in work_shifts_fact:
            if (not shift['dttm_work_start'] and shift["dttm_work_end"]) or (shift['dttm_work_start'] and not shift['dttm_work_end']):
                if shift["dt"] not in planned_dates:
                    unplanned_work_shifts_one_tick_count += 1
            elif shift['dttm_work_start'] and shift['dttm_work_end']:
                hours_fact = shift["dttm_work_end"]- shift["dttm_work_start"]
                if shift["dt"] not in planned_dates :
                    unplanned_work_shifts_count += 1
                    unplanned_work_shifts_hours += hours_fact.total_seconds() / 3600
            if isinstance(hours_fact, pd.Timedelta):
                delta_work_hours_fact += hours_fact.total_seconds() / 3600
    else:
        if row.dttm_work_end_fact and isinstance(row.dttm_work_end_fact, int):
            row.dttm_work_end_fact = pd.Timestamp(row.dttm_work_end_fact)
        if row.dttm_work_start_fact and isinstance(row.dttm_work_start_fact, int):
            row.dttm_work_start_fact = pd.Timestamp(row.dttm_work_start_fact)
        if row.dttm_work_end_fact and row.dttm_work_start_fact:
            delta_work_hours_fact = row.dttm_work_end_fact - row.dttm_work_start_fact
        if isinstance(delta_work_hours_fact, pd.Timedelta):
            delta_work_hours_fact = delta_work_hours_fact.total_seconds() / 3600
        if row["dt"].date not in planned_dates:
            if (not row.dttm_work_start_fact and row.dttm_work_end_fact) or (row.dttm_work_start_fact and not row.dttm_work_end_fact):
                unplanned_work_shifts_one_tick_count += 1
            elif row.dttm_work_start_fact and row.dttm_work_end_fact:
                unplanned_work_shifts_count += 1
                unplanned_work_shifts_hours += delta_work_hours_fact
    if len(work_shifts_plan) > 1:
        for shift in work_shifts_plan:
            if shift['dttm_work_start'] and shift['dttm_work_end']:
                hours_plan = shift["dttm_work_end"]- shift["dttm_work_start"]
                delta_work_hours_plan += hours_plan.total_seconds() / 3600

    plan_work_hours = max(row.plan_work_hours, delta_work_hours_plan)
    if len([x for x in work_shifts_plan if x['type'] == WorkerDay.TYPE_WORKDAY]):  # if at least one workday in plan, don't merge rows as doubled
        override_skip = True
    return plan_work_hours, override_skip, unplanned_work_shifts_one_tick_count, unplanned_work_shifts_hours, unplanned_work_shifts_count


def __check_duplicate_row(prev_row, cur_row):
    """Check if there is a duplicate row in the table"""
    check_cols = ["dt", "worker_fio", "user_network"]
    return prev_row[check_cols].equals(cur_row[check_cols]) and not prev_row["wd_type_id"] == cur_row["wd_type_id"]

def _write_data_rows(worksheet, df, columns, include_extra_columns, wd_types_dict, date_format, def_format, work_days):
    df["dt"] = pd.to_datetime(df["dt"], format="%Y-%m-%d")
    prev_row = skip_wd_type = None
    adjust_row = 0
    for i, row in df.iterrows():
        if skip_wd_type:
            adjust_row += 1
        plan_work_hours, override_skip,\
        unplanned_work_shifts_one_tick_count, unplanned_work_shifts_hours, unplanned_work_shifts_count = __calc_day_work_hours(row, work_days)
        if prev_row is not None and __check_duplicate_row(prev_row, row) and not override_skip:
            i -= 1
            skip_wd_type = True
        else:
            skip_wd_type = False
        row_num: int = 11 + i - adjust_row
        fact_work_hours = max(row.fact_work_hours, unplanned_work_shifts_hours)
        worker_day_type = wd_types_dict[row.wd_type_id].name
        work_type = row.work_type_name if (row.is_outsource or row.worker_fio == '-') else row.position_name
        network_shop = row.user_network if row.is_outsource else row.employment_shop_name
        is_outsource = 'не штат' if row.is_outsource else 'штат'
        if (row.is_outsource or row.shop_name != row.employment_shop_name) and row.wd_type_id == WorkerDay.TYPE_WORKDAY:
            worker_day_type = "Биржа смен"

        worksheet.write_number(row_num, columns['number'], i + 1 - adjust_row, def_format)
        if include_extra_columns:
            worksheet.write_string(row_num, columns['region'], row.region, def_format)
            worksheet.write_string(row_num, columns['region_manager'], row.region_manager, def_format)
            worksheet.write_string(row_num, columns['supervisor_mentor'], row.supervisor_mentor, def_format)
            worksheet.write_string(row_num, columns['supervisor'], row.supervisor, def_format)
        worksheet.write_string(row_num, columns['shop'], row.shop_name, def_format)
        worksheet.write_datetime(row_num, columns['date'], row['dt'], date_format)
        worksheet.write_string(row_num, columns['worker_fio'], row.worker_fio, def_format)
        worksheet.write_string(row_num, columns['tabel_code'], row.tabel_code, def_format)
        worksheet.write_string(row_num, columns['network_shop'], network_shop, def_format)
        worksheet.write_string(row_num, columns['is_outsource'],is_outsource , def_format)
        worksheet.write_string(row_num, columns['work_type'], work_type, def_format)
        if not skip_wd_type:  # overwriting whole row besides this column
            worksheet.write_string(row_num, columns['worker_day_type'], worker_day_type, def_format)
        worksheet.write_number(row_num, columns['plan_work_hours'], round(plan_work_hours, 2), def_format)
        worksheet.write_number(row_num, columns['fact_work_hours'], round(fact_work_hours, 2), def_format)
        worksheet.write_number(row_num, columns['manual_hours'], round(row.fact_manual_work_hours, 2), def_format)
        worksheet.write_number(row_num, columns['late_arrival_hours'], round(row.late_arrival_hours, 2), def_format)
        worksheet.write_number(row_num, columns['late_arrival_count'], row.late_arrival_count, def_format)
        worksheet.write_number(row_num, columns['early_arrival_hours'], round(row.early_arrival_hours, 2), def_format)
        worksheet.write_number(row_num, columns['early_arrival_count'], row.early_arrival_count, def_format)
        worksheet.write_number(row_num, columns['early_departure_hours'], round(row.early_departure_hours, 2), def_format)
        worksheet.write_number(row_num, columns['early_departure_count'], row.early_departure_count, def_format)
        worksheet.write_number(row_num, columns['late_departure_hours'], round(row.late_departure_hours, 2), def_format)
        worksheet.write_number(row_num, columns['late_departure_count'], row.late_departure_count, def_format)
        worksheet.write_number(row_num, columns['lost_hours'], round(row.lost_work_hours, 2), def_format)
        worksheet.write_number(row_num, columns['lost_count'], row.lost_work_hours_count, def_format)
        if include_extra_columns:
            worksheet.write_number(row_num, columns['unplanned_work_shifts_one_tick_count'], round(unplanned_work_shifts_one_tick_count, 2), def_format)
            worksheet.write_number(row_num, columns['unplanned_work_shifts_hours'], round(unplanned_work_shifts_hours, 2), def_format)
            worksheet.write_number(row_num, columns['unplanned_work_shifts_count'], round(unplanned_work_shifts_count, 2), def_format)
        prev_row = row

def create_data_frame(qs, unapplied_vacancies, extra_columns, include_extra_columns) -> pd.DataFrame:
    df = pd.DataFrame(list(qs.values(*values_df)), columns=list(set(columns_df)))
    unapplied_vacancies = list(
        unapplied_vacancies.values(
            'dt',
            'shop_name',
            'work_type_name',
            'plan_work_hours',
            'lost_work_hours',
            'lost_work_hours_count',
            'user_network',
            'is_outsource_allowed',
            'wd_type_id',
        )
    )
    if unapplied_vacancies:
        df = df.append(
            pd.DataFrame(unapplied_vacancies).rename({'is_outsource_allowed': 'is_outsource'}, axis=1),
            ignore_index=True,
        )

    df.fillna(
        dict.fromkeys(
            [
                'plan_work_hours',
                'fact_work_hours',
                'fact_manual_work_hours',
                'late_arrival_hours',
                'late_arrival_count',
                'early_arrival_hours',
                'early_arrival_count',
                'early_departure_hours',
                'early_departure_count',
                'late_departure_hours',
                'late_departure_count',
                'fact_without_plan_work_hours',
                'lost_work_hours',
                'lost_work_hours_count',
                'dttm_work_start_fact',
                'dttm_work_end_fact',
            ],
            0,
        ),
        inplace=True,
    )
    df.fillna(
        dict.fromkeys(
            [
                'worker_fio',
                'tabel_code',
                'user_network',
                'shop_name',
                'employment_shop_name',
                'position_name',
            ] + (list(extra_columns) if include_extra_columns else []),
            '-',
        ),
        inplace=True,
    )
    df = df.sort_values('dt', kind='mergesort').reset_index()
    df.replace(pd.NaT, 0, inplace=True)
    return df

def _filter_query(dt_from, dt_to, shop_ids, filters=None):
    shop_object = 'все'
    qs = ScheduleDeviations.objects.filter(dt__gte=dt_from, dt__lte=dt_to).filter(**filters)
    unapplied_vacancies = WorkerDay.objects.get_plan_approved(dt__gte=dt_from, dt__lte=dt_to, employee_id__isnull=True,
                                                              type__is_dayoff=False).annotate(
        work_type_name=Coalesce(
            Subquery(
                WorkerDayCashboxDetails.objects.filter(worker_day_id=OuterRef('id')).values(
                    'work_type__work_type_name__name')[:1]
            ),
            Value(""),
            output_field=CharField(),
        ),
        shop_name=F('shop__name'),
        plan_work_hours=Coalesce(Cast(Extract(F('work_hours'), 'epoch') / 3600, FloatField()), 0,
                                 output_field=FloatField()),
        lost_work_hours=F('plan_work_hours'),
        lost_work_hours_count=Value(1, IntegerField()),
        user_network=Subquery(
            WorkerDayOutsourceNetwork.objects.filter(workerday_id=OuterRef('id')).values('network__name')[:1]
        ),
        is_outsource_allowed=ExpressionWrapper(
            Q(user_network__isnull=False),
            output_field=BooleanField(),
        ),
        wd_type_id=F('type_id'),
    )
    if "work_type_name__in" in filters:
        unapplied_vacancies = unapplied_vacancies.filter(work_type_name__in=filters['work_type_name__in'])
    if "is_outsource" in filters:
        unapplied_vacancies = unapplied_vacancies.filter(is_outsource=filters['is_outsource'])
    if shop_ids:
        qs = qs.filter(
            Q(shop_id__in=shop_ids) |
            Q(employee_id__in=Employment.objects.get_active(
                dt_from=dt_from,
                dt_to=dt_to,
                shop_id__in=shop_ids,
            ).values_list('employee_id'))
        )
        unapplied_vacancies = unapplied_vacancies.filter(shop_id__in=shop_ids)
        shop_object = ', '.join(Shop.objects.filter(id__in=shop_ids).values_list('name', flat=True))
    return qs, unapplied_vacancies, shop_object


def schedule_deviation_report(dt_from, dt_to, created_by_id=None, shop_ids=None, filters=None):
    user_created = 'автоматически'
    wd_types_dict = WorkerDayType.get_wd_types_dict()
    user_created_fio = ''
    work_days = WorkerDay.objects.select_related(
             'type', 'employee', 'employee__user').filter(dt__gte=dt_from, dt__lte=dt_to, is_approved=True,)
    if shop_ids:
        work_days = work_days.select_related('shop').filter(shop_id__in=shop_ids)
    work_days = work_days.values('dt', 'shop__name', 'employee__user__last_name',
                      'type', 'dttm_work_start', 'dttm_work_end', 'dttm_work_start_tabel',
                      'dttm_work_end_tabel', 'is_fact'
                    )
    if created_by_id:
        user_created = User.objects.get(id=created_by_id)
        user_created_fio = user_created.get_fio()
    qs, unapplied_vacancies, shop_object = _filter_query(dt_from, dt_to, shop_ids, filters=filters)

    if include_extra_columns := (created_by_id and
                                 user_created.network.settings_values_prop.get(
                                     'include_region_and_supervisor_in_schedule_deviation_report')):
        extra_columns = _get_extra_columns_dict(dt_from, dt_to)
        qs = qs.annotate(**extra_columns)
        values_df.extend(extra_columns)
        columns_df.extend(extra_columns)
    else:
        extra_columns = None

    if include_extra_columns:
        columns_list = [el['col_name'] for el in table_columns]
    else:
        columns_list = [el['col_name'] for el in table_columns if not el.get('is_extra')]
    columns_list += ['dttm_work_start_fact', 'dttm_work_end_fact']
    columns = {column: i for i, column in enumerate(columns_list)}
    df: pd.DataFrame = create_data_frame(qs, unapplied_vacancies, extra_columns, include_extra_columns)

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})

    worksheet = workbook.add_worksheet(f'{dt_from}-{dt_to}')
    def_format = workbook.add_format(def_style)
    header_format = workbook.add_format(header_style)
    date_format = workbook.add_format(date_style)

    _write_header(worksheet, dt_from, dt_to, shop_object, user_created_fio)
    _stylize_sheet(worksheet, columns, header_format, include_extra_columns)
    _write_data_rows(worksheet, df, columns, include_extra_columns, wd_types_dict, date_format, def_format, list(work_days))
    workbook.close()
    output.seek(0)
    return output


def _get_extra_columns_dict(dt_from: date, dt_to: date) -> OrderedDict:
    depth = 3 # Shop parent/child lookup depth
    child_lookup1 = (Q(**{'__'.join(['child']*d): OuterRef('shop')}) for d in range(1, depth+1))      # 1 OuterRef
    child_lookup1 = reduce(lambda x, y: x|y, child_lookup1)                                           # Q(child=OuterRef('shop')) | Q(child__child=OuterRef('shop')) | ...

    region_sq = Subquery(Shop.objects.filter(child_lookup1, name__startswith='Регион').values('name')[:1])
    region_manager_sq = _get_deep_employee_fio_subquery(
        dt_from=dt_from,
        dt_to=dt_to,
        shop__name=OuterRef(OuterRef('region')),
        position__name='Руководитель региона'
    )

    child_lookup2 = (Q(**{'__'.join(['child']*d): OuterRef(OuterRef(OuterRef('shop')))}) for d in range(1, depth+1))  # 3 OuterRefs
    child_lookup2 = reduce(lambda x, y: x|y, child_lookup2)
    shops_sq = Subquery(Shop.objects.filter(child_lookup2).values('id'))
    supervisor_mentor_sq = _get_deep_employee_fio_subquery(
        dt_from=dt_from,
        dt_to=dt_to,
        shop_id__in=shops_sq,
        position__name='Супервайзер-наставник'
    )

    supervisor_sq = _get_deep_employee_fio_subquery(
        dt_from=dt_from,
        dt_to=dt_to,
        shop_id__in=shops_sq,
        position__name='Супервайзер'
    )

    return OrderedDict((
        # Region name / Название региона (shop_name)
        ('region', region_sq),
        # Region managet (Full name of user) / Руководитель региона (ФИО user)
        ('region_manager', region_manager_sq),
        # Supervisor mentor (Full name of user) / Наставник супервайзера (ФИО user)
        ('supervisor_mentor', supervisor_mentor_sq),
        # Supervisor (Full name of user) / Супервайзер (ФИО user)
        ('supervisor', supervisor_sq)
    ))    


def _get_deep_employee_fio_subquery(**kwargs):
    return Subquery(
        User.objects.filter(
            employees__employments__in=Employment.objects.get_active(
                **kwargs
            )[:1]
        ).annotate(
            fio=Concat('last_name', Value(' '), 'first_name', Value(' '), 'middle_name')
        ).values(
            'fio'
        )[:1]
    )
