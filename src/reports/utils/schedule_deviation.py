from datetime import date
from collections import OrderedDict
from functools import reduce
import io
import pandas as pd
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


def schedule_deviation_report(
    dt_from: date,
    dt_to: date,
    created_by_id=None,
    shop_ids=None,
    filters: dict = {}
) -> bytes:

    shop_object = 'все'
    user_created = 'автоматически'
    wd_types_dict = WorkerDayType.get_wd_types_dict()

    if created_by_id:
        user_created = User.objects.get(id=created_by_id)
        user_created_fio = user_created.get_fio()

    qs = ScheduleDeviations.objects.filter(dt__gte=dt_from, dt__lte=dt_to).filter(**filters)
    unapplied_vacancies = WorkerDay.objects.get_plan_approved(dt__gte=dt_from, dt__lte=dt_to, employee_id__isnull=True, type__is_dayoff=False).annotate(
        work_type_name=Coalesce(
            Subquery(
                WorkerDayCashboxDetails.objects.filter(worker_day_id=OuterRef('id')).values('work_type__work_type_name__name')[:1]
            ),
            Value(""),
            output_field=CharField(),
        ),
        shop_name=F('shop__name'),
        plan_work_hours=Coalesce(Cast(Extract(F('work_hours'), 'epoch') / 3600, FloatField()), 0, output_field=FloatField()),
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
            Q(shop_id__in=shop_ids)|
            Q(employee_id__in=Employment.objects.get_active(
                dt_from=dt_from,
                dt_to=dt_to, 
                shop_id__in=shop_ids,
            ).values_list('employee_id'))
        )
        unapplied_vacancies = unapplied_vacancies.filter(shop_id__in=shop_ids)
        shop_object = ', '.join(Shop.objects.filter(id__in=shop_ids).values_list('name', flat=True))

    values_df = [
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
        'fact_without_plan_count',
        'lost_work_hours',
        'lost_work_hours_count',
        'wd_type_id',
        'employment_shop_name',
        'position_name',
    ]
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
        'fact_without_plan_count',
        'lost_work_hours',
        'lost_work_hours_count',
        'wd_type_id',
        'employment_shop_name',
        'position_name',
    ]
    if  include_extra_columns := (created_by_id and \
            user_created.network.settings_values_prop.get('include_region_and_supervisor_in_schedule_deviation_report')):
        extra_columns = _get_extra_columns_dict(dt_from, dt_to)
        qs = qs.annotate(**extra_columns)
        values_df.extend(extra_columns)
        columns_df.extend(extra_columns)
    
    df = pd.DataFrame(list(qs.values(*values_df)), columns=columns_df)
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
                'fact_without_plan_count',
                'lost_work_hours',
                'lost_work_hours_count',
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

    columns_list = [
        'number',
        'shop',
        'date',
        'fio',
        'tabel_code',
        'network_shop',
        'is_outsource',
        'work_type',
        'worker_day_type',
        'plan_hours',
        'fact_hours',
        'manual_hours',
        'late_arrival_hours',
        'late_arrival_count',
        'early_arrival_hours',
        'early_arrival_count',
        'early_departure_hours',
        'early_departure_count',
        'late_departure_hours',
        'late_departure_count',
        'fact_without_plan_hours',
        'fact_without_plan_count',
        'lost_hours',
        'lost_count'
    ]
    if include_extra_columns:
        columns_list = columns_list[:1] + list(extra_columns) + columns_list[1:]

    columns = {column:i for i, column in enumerate(columns_list)}

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})

    worksheet = workbook.add_worksheet(f'{dt_from}-{dt_to}')

    def_format = workbook.add_format({
        'border': 1,
        'valign': 'vcenter',
        'align': 'center',
        'text_wrap': True,
    })
    header_format = workbook.add_format({
        'border': 1,
        'bold': True,
        'text_wrap': True,
        'valign': 'vcenter',
        'align': 'center',
        'bg_color': '#d9d9d9',
    })
    date_format = workbook.add_format({
        'border': 1,
        'valign': 'vcenter',
        'align': 'center',
        'text_wrap': True,
        'num_format': 'dd.mm.yyyy',
    })

    # add info
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

    # main info
    worksheet.write_string(10, columns['number'], '№', header_format)
    if include_extra_columns:
        worksheet.write_string(10, columns['region'], 'Регион', header_format)
        worksheet.write_string(10, columns['region_manager'], 'РР', header_format)
        worksheet.write_string(10, columns['supervisor_mentor'], 'СВН', header_format)
        worksheet.write_string(10, columns['supervisor'], 'СВ', header_format)
    worksheet.write_string(10, columns['shop'], 'Магазин/объект', header_format)
    worksheet.write_string(10, columns['date'], 'Дата', header_format)
    worksheet.write_string(10, columns['fio'], 'Сотрудник', header_format)
    worksheet.write_string(10, columns['tabel_code'], 'Табельный Номер', header_format)
    worksheet.write_string(10, columns['network_shop'], 'Закрепленная компания/магазин', header_format)
    worksheet.write_string(10, columns['is_outsource'], 'Штат или нет', header_format)
    worksheet.write_string(10, columns['work_type'], 'Должность/вид работ', header_format)
    worksheet.write_string(10, columns['worker_day_type'], 'Тип дня', header_format)
    worksheet.write_string(10, columns['plan_hours'], 'План', header_format)
    worksheet.write_string(10, columns['fact_hours'], 'Факт', header_format)
    worksheet.write_string(10, columns['manual_hours'], 'Скорректировано вручную', header_format)
    worksheet.write_string(10, columns['late_arrival_hours'], 'Опоздание часы', header_format)
    worksheet.write_string(10, columns['late_arrival_count'], 'Опоздания кол-во раз', header_format)
    worksheet.write_string(10, columns['early_arrival_hours'], 'Ранний приход на работу часы', header_format)
    worksheet.write_string(10, columns['early_arrival_count'], 'Ранний приход на работу количество раз', header_format)
    worksheet.write_string(10, columns['early_departure_hours'], 'Ранний уход часы', header_format)
    worksheet.write_string(10, columns['early_departure_count'], 'Ранний уход с работы количество раз', header_format)
    worksheet.write_string(10, columns['late_departure_hours'], 'Поздний уход с работы часы', header_format)
    worksheet.write_string(10, columns['late_departure_count'], 'Поздний уход с работы_количество раз', header_format)
    worksheet.write_string(10, columns['fact_without_plan_hours'], 'Выход на работу вне плана часы', header_format)
    worksheet.write_string(10, columns['fact_without_plan_count'], 'Выход на работу вне плана количество раз', header_format)
    worksheet.write_string(10, columns['lost_hours'], 'Потерянное время часы', header_format)
    worksheet.write_string(10, columns['lost_count'], 'Потерянное время количество раз', header_format)

    # set cols
    worksheet.set_column(columns['number'], columns['number'], 4)
    if include_extra_columns:
        worksheet.set_column(columns['region'], columns['region'], 25)
        worksheet.set_column(columns['region_manager'], columns['region_manager'], 25)
        worksheet.set_column(columns['supervisor_mentor'], columns['supervisor_mentor'], 25)
        worksheet.set_column(columns['supervisor'], columns['supervisor'], 25)
    worksheet.set_column(columns['shop'], columns['shop'], 36)
    worksheet.set_column(columns['date'], columns['date'], 20)
    worksheet.set_column(columns['fio'], columns['fio'], 33)
    worksheet.set_column(columns['tabel_code'], columns['tabel_code'], 22)
    worksheet.set_column(columns['network_shop'], columns['network_shop'], 36)
    worksheet.set_column(columns['is_outsource'], columns['is_outsource'], 14)
    worksheet.set_column(columns['work_type'], columns['work_type'], 18)
    worksheet.set_column(columns['worker_day_type'], columns['worker_day_type'], 18)
    worksheet.set_column(columns['plan_hours'], columns['plan_hours'], 9)
    worksheet.set_column(columns['fact_hours'], columns['fact_hours'], 9)
    worksheet.set_column(columns['manual_hours'], columns['manual_hours'], 18)
    worksheet.set_column(columns['late_arrival_hours'], columns['late_arrival_hours'], 13)
    worksheet.set_column(columns['late_arrival_count'], columns['late_arrival_count'], 11)
    worksheet.set_column(columns['early_arrival_hours'], columns['early_arrival_hours'], 13)
    worksheet.set_column(columns['early_arrival_count'], columns['early_arrival_count'], 14)
    worksheet.set_column(columns['early_departure_hours'], columns['early_departure_hours'], 13)
    worksheet.set_column(columns['early_departure_count'], columns['early_departure_count'], 13)
    worksheet.set_column(columns['late_departure_hours'], columns['late_departure_hours'], 13)
    worksheet.set_column(columns['late_departure_count'], columns['late_departure_count'], 14)
    worksheet.set_column(columns['fact_without_plan_hours'], columns['fact_without_plan_hours'], 11)
    worksheet.set_column(columns['fact_without_plan_count'], columns['fact_without_plan_count'], 13)
    worksheet.set_column(columns['lost_hours'], columns['lost_hours'], 14)
    worksheet.set_column(columns['lost_count'], columns['lost_count'], 17)

    for i, row in df.iterrows():
        worker_day_type = wd_types_dict[row.wd_type_id].name
        if (row.is_outsource or row.shop_name != row.employment_shop_name) and row.wd_type_id == WorkerDay.TYPE_WORKDAY:
            worker_day_type = "Биржа смен"
        worksheet.write_number(11 + i, columns['number'], i+1, def_format)
        if include_extra_columns:
            worksheet.write_string(11 + i, columns['region'], row.region, def_format)
            worksheet.write_string(11 + i, columns['region_manager'], row.region_manager, def_format)
            worksheet.write_string(11 + i, columns['supervisor_mentor'], row.supervisor_mentor, def_format)
            worksheet.write_string(11 + i, columns['supervisor'], row.supervisor, def_format)
        worksheet.write_string(11 + i, columns['shop'], row.shop_name, def_format)
        worksheet.write_datetime(11 + i, columns['date'], row['dt'], date_format)
        worksheet.write_string(11 + i, columns['fio'], row.worker_fio, def_format)
        worksheet.write_string(11 + i, columns['tabel_code'], row.tabel_code, def_format)
        worksheet.write_string(11 + i, columns['network_shop'], row.user_network if row.is_outsource else row.employment_shop_name, def_format)
        worksheet.write_string(11 + i, columns['is_outsource'], 'не штат' if row.is_outsource else 'штат', def_format)
        worksheet.write_string(11 + i, columns['work_type'], row.work_type_name if (row.is_outsource or row.worker_fio == '-') else row.position_name, def_format)
        worksheet.write_string(11 + i, columns['worker_day_type'], worker_day_type, def_format)
        worksheet.write_number(11 + i, columns['plan_hours'], round(row.plan_work_hours, 2), def_format)
        worksheet.write_number(11 + i, columns['fact_hours'], round(row.fact_work_hours, 2), def_format)
        worksheet.write_number(11 + i, columns['manual_hours'], round(row.fact_manual_work_hours, 2), def_format)
        worksheet.write_number(11 + i, columns['late_arrival_hours'], round(row.late_arrival_hours, 2), def_format)
        worksheet.write_number(11 + i, columns['late_arrival_count'], row.late_arrival_count, def_format)
        worksheet.write_number(11 + i, columns['early_arrival_hours'], round(row.early_arrival_hours, 2), def_format)
        worksheet.write_number(11 + i, columns['early_arrival_count'], row.early_arrival_count, def_format)
        worksheet.write_number(11 + i, columns['early_departure_hours'], round(row.early_departure_hours, 2), def_format)
        worksheet.write_number(11 + i, columns['early_departure_count'], row.early_departure_count, def_format)
        worksheet.write_number(11 + i, columns['late_departure_hours'], round(row.late_departure_hours, 2), def_format)
        worksheet.write_number(11 + i, columns['late_departure_count'], row.late_departure_count, def_format)
        worksheet.write_number(11 + i, columns['fact_without_plan_hours'], round(row.fact_without_plan_work_hours, 2), def_format)
        worksheet.write_number(11 + i, columns['fact_without_plan_count'], row.fact_without_plan_count, def_format)
        worksheet.write_number(11 + i, columns['lost_hours'], round(row.lost_work_hours, 2), def_format)
        worksheet.write_number(11 + i, columns['lost_count'], row.lost_work_hours_count, def_format)

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
