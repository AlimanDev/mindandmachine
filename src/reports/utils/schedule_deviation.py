from datetime import date
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
from django.db.models.functions import Coalesce, Extract, Cast
from django.http.response import HttpResponse
from django.utils.encoding import escape_uri_path
import xlsxwriter
from src.base.models import Employment, Shop, User

from src.timetable.models import (
    ScheduleDeviations, 
    WorkerDay, 
    WorkerDayCashboxDetails, 
    WorkerDayOutsourceNetwork,
    WorkerDayType,
)


def schedule_deviation_report(dt_from, dt_to, *args, title=None, in_memory=False, created_by_id=None, shop_ids=None, **kwargs):

    shop_object = 'все'
    user_created = 'автоматически'
    wd_types_dict = WorkerDayType.get_wd_types_dict()

    if created_by_id:
        user_created = User.objects.get(id=created_by_id).get_fio()

    if not title:
        title = f'Schedule_deviation_{dt_from}-{dt_to}.xlsx'

    data = ScheduleDeviations.objects.filter(dt__gte=dt_from, dt__lte=dt_to).filter(*args, **kwargs)
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

    if "work_type_name__in" in kwargs:
        unapplied_vacancies = unapplied_vacancies.filter(work_type_name__in=kwargs['work_type_name__in'])
    if "is_outsource" in kwargs:
        unapplied_vacancies = unapplied_vacancies.filter(is_outsource=kwargs['is_outsource'])

    if shop_ids:
        data = data.filter(
            Q(shop_id__in=shop_ids)|
            Q(employee_id__in=Employment.objects.get_active(
                dt_from=dt_from,
                dt_to=dt_to, 
                shop_id__in=shop_ids,
            ).values_list('employee_id'))
        )
        unapplied_vacancies = unapplied_vacancies.filter(shop_id__in=shop_ids)
        shop_object = ', '.join(Shop.objects.filter(id__in=shop_ids).values_list('name', flat=True))

    df = pd.DataFrame(
        list(
            data.values(
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
            )
        ),
        columns=[
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
        ],
    )
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
            ],
            '-',
        ),
        inplace=True,
    )
    df = df.sort_values('dt', kind='mergesort').reset_index()

    NUMBER = 0
    SHOP = 1
    DATE = 2
    FIO = 3
    TABEL_CODE = 4
    NETWORK_SHOP = 5
    IS_OUTSOURCE = 6
    WORK_TYPE = 7
    WORKERDAY_TYPE = 8
    PLAN_HOURS = 9
    FACT_HOURS = 10
    MANUAL_HOURS = 11
    LATE_ARRIVAL_HOURS = 12
    LATE_ARRIVAL_COUNT = 13
    EARLY_ARRIVAL_HOURS = 14
    EARLY_ARRIVAL_COUNT = 15
    EARLY_DEPARTURE_HOURS = 16
    EARLY_DEPARTURE_COUNT = 17
    LATE_DEPARTURE_HOURS = 18
    LATE_DEPARTURE_COUNT = 19
    FACT_WITHOUT_PLAN_HOURS = 20
    FACT_WITHOUT_PLAN_COUNT = 21
    LOST_HOURS = 22
    LOST_COUNT = 23

    if in_memory:
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    else:
        workbook = xlsxwriter.Workbook(title)

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
    worksheet.write_string(8, 3, user_created)

    # main info
    worksheet.write_string(10, NUMBER, '№', header_format)
    worksheet.write_string(10, SHOP, 'Магазин/объект', header_format)
    worksheet.write_string(10, DATE, 'Дата', header_format)
    worksheet.write_string(10, FIO, 'Сотрудник', header_format)
    worksheet.write_string(10, TABEL_CODE, 'Табельный Номер', header_format)
    worksheet.write_string(10, NETWORK_SHOP, 'Закрепленная компания/магазиня', header_format)
    worksheet.write_string(10, IS_OUTSOURCE, 'Штат или нет', header_format)
    worksheet.write_string(10, WORK_TYPE, 'Должность/вид работ', header_format)
    worksheet.write_string(10, WORKERDAY_TYPE, 'Тип дня', header_format)
    worksheet.write_string(10, PLAN_HOURS, 'План', header_format)
    worksheet.write_string(10, FACT_HOURS, 'Факт', header_format)
    worksheet.write_string(10, MANUAL_HOURS, 'Скорректировано вручную', header_format)
    worksheet.write_string(10, LATE_ARRIVAL_HOURS, 'Опоздание часы', header_format)
    worksheet.write_string(10, LATE_ARRIVAL_COUNT, 'Опоздания кол-во раз', header_format)
    worksheet.write_string(10, EARLY_ARRIVAL_HOURS, 'Ранний приход на работу часы', header_format)
    worksheet.write_string(10, EARLY_ARRIVAL_COUNT, 'Ранний приход на работу количество раз', header_format)
    worksheet.write_string(10, EARLY_DEPARTURE_HOURS, 'Ранний уход часы', header_format)
    worksheet.write_string(10, EARLY_DEPARTURE_COUNT, 'Ранний уход с работы количество раз', header_format)
    worksheet.write_string(10, LATE_DEPARTURE_HOURS, 'Поздний уход с работы часы', header_format)
    worksheet.write_string(10, LATE_DEPARTURE_COUNT, 'Поздний уход с работы_количество раз', header_format)
    worksheet.write_string(10, FACT_WITHOUT_PLAN_HOURS, 'Выход на работу вне плана часы', header_format)
    worksheet.write_string(10, FACT_WITHOUT_PLAN_COUNT, 'Выход на работу вне плана количество раз', header_format)
    worksheet.write_string(10, LOST_HOURS, 'Потерянное время часы', header_format)
    worksheet.write_string(10, LOST_COUNT, 'Потерянное время количество раз', header_format)

    # set cols
    worksheet.set_column(NUMBER, NUMBER, 4)
    worksheet.set_column(SHOP, SHOP, 36)
    worksheet.set_column(DATE, DATE, 20)
    worksheet.set_column(FIO, FIO, 33)
    worksheet.set_column(TABEL_CODE, TABEL_CODE, 22)
    worksheet.set_column(NETWORK_SHOP, NETWORK_SHOP, 36)
    worksheet.set_column(IS_OUTSOURCE, IS_OUTSOURCE, 14)
    worksheet.set_column(WORK_TYPE, WORK_TYPE, 18)
    worksheet.set_column(WORKERDAY_TYPE, WORKERDAY_TYPE, 18)
    worksheet.set_column(PLAN_HOURS, PLAN_HOURS, 9)
    worksheet.set_column(FACT_HOURS, FACT_HOURS, 9)
    worksheet.set_column(MANUAL_HOURS, MANUAL_HOURS, 18)
    worksheet.set_column(LATE_ARRIVAL_HOURS, LATE_ARRIVAL_HOURS, 13)
    worksheet.set_column(LATE_ARRIVAL_COUNT, LATE_ARRIVAL_COUNT, 11)
    worksheet.set_column(EARLY_ARRIVAL_HOURS, EARLY_ARRIVAL_HOURS, 13)
    worksheet.set_column(EARLY_ARRIVAL_COUNT, EARLY_ARRIVAL_COUNT, 14)
    worksheet.set_column(EARLY_DEPARTURE_HOURS, EARLY_DEPARTURE_HOURS, 13)
    worksheet.set_column(EARLY_DEPARTURE_COUNT, EARLY_DEPARTURE_COUNT, 13)
    worksheet.set_column(LATE_DEPARTURE_HOURS, LATE_DEPARTURE_HOURS, 13)
    worksheet.set_column(LATE_DEPARTURE_COUNT, LATE_DEPARTURE_COUNT, 14)
    worksheet.set_column(FACT_WITHOUT_PLAN_HOURS, FACT_WITHOUT_PLAN_HOURS, 11)
    worksheet.set_column(FACT_WITHOUT_PLAN_COUNT, FACT_WITHOUT_PLAN_COUNT, 13)
    worksheet.set_column(LOST_HOURS, LOST_HOURS, 14)
    worksheet.set_column(LOST_COUNT, LOST_COUNT, 17)

    for i, row in df.iterrows():
        worker_day_type = wd_types_dict[row.wd_type_id].name
        if (row.is_outsource or row.shop_name != row.employment_shop_name) and row.wd_type_id == WorkerDay.TYPE_WORKDAY:
            worker_day_type = "Биржа смен"
        worksheet.write_number(11 + i, NUMBER, i+1, def_format)
        worksheet.write_string(11 + i, SHOP, row.shop_name, def_format)
        worksheet.write_datetime(11 + i, DATE, row['dt'], date_format)
        worksheet.write_string(11 + i, FIO, row.worker_fio, def_format)
        worksheet.write_string(11 + i, TABEL_CODE, row.tabel_code, def_format)
        worksheet.write_string(11 + i, NETWORK_SHOP, row.user_network if row.is_outsource else row.employment_shop_name, def_format)
        worksheet.write_string(11 + i, IS_OUTSOURCE, 'не штат' if row.is_outsource else 'штат', def_format)
        worksheet.write_string(11 + i, WORK_TYPE, row.work_type_name if (row.is_outsource or row.worker_fio == '-') else row.position_name, def_format)
        worksheet.write_string(11 + i, WORKERDAY_TYPE, worker_day_type, def_format)
        worksheet.write_number(11 + i, PLAN_HOURS, round(row.plan_work_hours, 2), def_format)
        worksheet.write_number(11 + i, FACT_HOURS, round(row.fact_work_hours, 2), def_format)
        worksheet.write_number(11 + i, MANUAL_HOURS, round(row.fact_manual_work_hours, 2), def_format)
        worksheet.write_number(11 + i, LATE_ARRIVAL_HOURS, round(row.late_arrival_hours, 2), def_format)
        worksheet.write_number(11 + i, LATE_ARRIVAL_COUNT, row.late_arrival_count, def_format)
        worksheet.write_number(11 + i, EARLY_ARRIVAL_HOURS, round(row.early_arrival_hours, 2), def_format)
        worksheet.write_number(11 + i, EARLY_ARRIVAL_COUNT, row.early_arrival_count, def_format)
        worksheet.write_number(11 + i, EARLY_DEPARTURE_HOURS, round(row.early_departure_hours, 2), def_format)
        worksheet.write_number(11 + i, EARLY_DEPARTURE_COUNT, row.early_departure_count, def_format)
        worksheet.write_number(11 + i, LATE_DEPARTURE_HOURS, round(row.late_departure_hours, 2), def_format)
        worksheet.write_number(11 + i, LATE_DEPARTURE_COUNT, row.late_departure_count, def_format)
        worksheet.write_number(11 + i, FACT_WITHOUT_PLAN_HOURS, round(row.fact_without_plan_work_hours, 2), def_format)
        worksheet.write_number(11 + i, FACT_WITHOUT_PLAN_COUNT, row.fact_without_plan_count, def_format)
        worksheet.write_number(11 + i, LOST_HOURS, round(row.lost_work_hours, 2), def_format)
        worksheet.write_number(11 + i, LOST_COUNT, row.lost_work_hours_count, def_format)

    workbook.close()
    if in_memory:
        output.seek(0)
        return {
            'name': title,
            'file': output,
            'type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }

def schedule_deviation_report_response(dt_from, dt_to, *args, created_by_id=None, shop_ids=None, **kwargs):
    output = schedule_deviation_report(dt_from, dt_to, in_memory=True, created_by_id=created_by_id, shop_ids=shop_ids, **kwargs)

    response = HttpResponse(
        output['file'],
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="{}.xlsx"'.format(escape_uri_path(output['name']))
    return response
