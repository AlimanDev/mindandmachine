from src.util.utils import api_method
from .utils import xlsx_method
from .forms import (
    GetTable,
    GetDemandXlsxForm,
    GetUrvXlsxForm,
)
from src.main.shop.forms import GetDepartmentListForm
from src.main.shop.utils import get_shop_list_stats
from src.main.urv.utils import tick_stat_count_details

from src.db.models import (
    Shop,
    User,
    WorkerDay,
    PeriodClients,
    OperationType,
    WorkType,
    AttendanceRecords,
)

from datetime import time, timedelta, datetime, date
from dateutil.relativedelta import relativedelta
from django.apps import apps
from src.util.utils import JsonResponse
from src.util.models_converter import AttendanceRecordsConverter

from .xlsx.tabel import Tabel_xlsx
from src.util.forms import FormUtil
import json
import pandas as pd


@api_method('GET', GetTable)
@xlsx_method
def get_tabel(request, workbook, form):
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
    ws = workbook.add_worksheet(Tabel_xlsx.MONTH_NAMES[form['weekday'].month])

    shop = request.shop
    checkpoint = FormUtil.get_checkpoint(form)

    tabel = Tabel_xlsx(
        workbook,
        shop,
        form['weekday'],
        worksheet=ws,
        prod_days=None
    )


    from_dt = tabel.prod_days[0].dt
    to_dt = tabel.prod_days[-1].dt

    records = list(AttendanceRecords.objects.select_related('user').filter(
        dttm__date__gte=from_dt,
        dttm__date__lte=to_dt,
        shop_id=shop.id,
    ).order_by('dttm', 'user'))
    tick_stat = tick_stat_count_details(records)

    users = list(User.objects.qos_filter_active(
        dt_from=tabel.prod_days[-1].dt,
        dt_to=tabel.prod_days[0].dt,
        shop=shop,
    ).select_related('position').order_by('position_id', 'last_name', 'first_name', 'tabel_code'))

    breaktimes = json.loads(shop.break_triplets)
    breaktimes = list(map(lambda x: (x[0] / 60, x[1] / 60, sum(x[2]) / 60), breaktimes))

    workdays = WorkerDay.objects.qos_filter_version(checkpoint).select_related('worker').filter(
        worker__in=users,
        dt__gte=tabel.prod_days[0].dt,
        dt__lte=tabel.prod_days[-1].dt,
    ).order_by('worker__position_id', 'worker__last_name', 'worker__first_name', 'worker__tabel_code', 'dt')

    if form.get('inspection_version', False):
        tabel.change_for_inspection(tabel.prod_month.norm_work_hours, workdays)

    tabel.format_cells(len(users))
    tabel.add_main_info()

    # construct day
    tabel.construct_dates('%d', 12, 6, int)

    # construct weekday
    tabel.construct_dates('%w', 14, 6)

    # construct day 2
    tabel.construct_dates('d%d', 15, 6)

    tabel.construnts_users_info(users, 16, 0, ['code', 'fio', 'position', 'hired'], extra_row=True)

    tabel.fill_table(workdays, users, breaktimes, tick_stat, 16, 6)

    tabel.add_xlsx_functions(len(users), 12, 37, extra_row=True)

    tabel.add_sign(16 + len(users) * 2 + 2)

    return workbook, 'Tabel'


@api_method('GET', GetDemandXlsxForm)
@xlsx_method
def get_demand_xlsx(request, workbook, form):
    """
    Скачивает спрос по "клиентам" в эксель формате

    Args:
        method: GET
        url: /api/download/get_demand_xlsx
        from_dt(QOS_DATE): с какой даты скачивать
        to_dt(QOS_DATE): по какую дату скачивать
        shop_id(int): в каком магазинеde
        demand_model(char): 'C'/'Q'/'P'

    Returns:
        эксель файл с форматом Тип работ | Время | Значение
    """
    from_dt = form['from_dt']
    to_dt = form['to_dt']

    shop = Shop.objects.get(id=form['shop_id'])
    timestep = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute  # minutes

    model_form_dict = {
        'C': 'clients',
        'Q': 'queues',
        'P': 'products'
    }

    if (to_dt - from_dt).days > 90:
        return JsonResponse.internal_error('Выберите, пожалуйста, период не больше 90 дней.'), 'error'

    worksheet = workbook.add_worksheet('{}-{}'.format(from_dt.strftime('%Y.%m.%d'), to_dt.strftime('%Y.%m.%d')))
    worksheet.set_column(0, 3, 30)
    worksheet.write(0, 0, 'Тип работ')
    worksheet.write(0, 1, 'Время')
    worksheet.write(0, 2, 'Значение(долгосрочный)')
    worksheet.write(0, 3, 'Значение(фактический)')

    try:
        model = apps.get_model('db', 'period{}'.format(
            model_form_dict[form['demand_model']]
        ))
    except LookupError:
        return JsonResponse.internal_error('incorrect demand model'), 'error'

    period_demands = list(model.objects.select_related('operation_type__work_type').filter(
        operation_type__work_type__shop_id=form['shop_id'],
        dttm_forecast__date__gte=from_dt,
        dttm_forecast__date__lte=to_dt,
        type__in=[PeriodClients.FACT_TYPE, PeriodClients.LONG_FORECASE_TYPE]
    ).order_by('dttm_forecast', 'operation_type_id', 'type'))

    work_types = list(WorkType.objects.filter(shop_id=form['shop_id']).order_by('id'))
    operation_types = list(OperationType.objects.filter(work_type__in=work_types).order_by('id'))
    amount_operation_types = len(operation_types)

    dttm = datetime.combine(from_dt, time(0, 0))
    expected_record_amount = (to_dt - from_dt).days * amount_operation_types * 24 * 60 // timestep

    demand_index = 0
    period_demands_len = len(period_demands)
    if period_demands_len == 0:
        demand = model()  # null model if no data

    for index in range(expected_record_amount):
        operation_type_index = index % amount_operation_types
        operation_type = operation_types[operation_type_index]
        work_type = operation_type.work_type

        # work_type_index = index % amount_work_types
        # work_type_name = work_types[work_type_index].name

        if period_demands_len > demand_index:
            demand = period_demands[demand_index]

        worksheet.write(index + 1, 0, work_type.name + ' ' + operation_type.name)
        worksheet.write(index + 1, 1, dttm.strftime('%d.%m.%Y %H:%M:%S'))

        if (demand.dttm_forecast == dttm and
            demand.operation_type.work_type.name == work_type.name and
            demand.operation_type.name == operation_type.name):
            if demand.type == PeriodClients.FACT_TYPE:
                worksheet.write(index + 1, 3, round(demand.value, 1))
                demand_index += 1

                if index != expected_record_amount - 1:
                    next_demand = period_demands[demand_index]
                    if next_demand.type == PeriodClients.LONG_FORECASE_TYPE and \
                            next_demand.dttm_forecast == demand.dttm_forecast and \
                            next_demand.operation_type.work_type.name == demand.operation_type.work_type.name:
                        worksheet.write(index + 1, 2, round(next_demand.value, 1))
                        demand_index += 1
            else:
                worksheet.write(index + 1, 2, round(demand.value, 1))
                worksheet.write(index + 1, 3, 'Нет данных')
                demand_index += 1

        else:
            worksheet.write(index + 1, 2, 'Нет данных')
            worksheet.write(index + 1, 3, 'Нет данных')
        if index % amount_operation_types == amount_operation_types - 1 and index != 0:
            dttm += timedelta(minutes=timestep)

    return workbook, '{} {}-{}'.format(
        model_form_dict[form['demand_model']],
        from_dt.strftime('%Y.%m.%d'),
        to_dt.strftime('%Y.%m.%d'),
    )


@api_method('GET', GetUrvXlsxForm)
@xlsx_method
def get_urv_xlsx(request, workbook, form):
    """
    Скачивает записи по урв за запрошенную дату

    Args:
        method: GET
        url: /api/download/get_urv_xlsx
        from_dt(QOS_DATE): с какой даты скачивать
        to_dt(QOS_DATE): по какую дату скачивать
        shop_id(int): в каком магазинеde

    Returns:
        эксель файл с форматом Дата | Фамилия Имя сотрудника, табельный номер | Время | Тип
    """
    shop_id = form['shop_id']
    from_dt = form['from_dt']
    to_dt = form['to_dt']

    worksheet = workbook.add_worksheet('{}-{}'.format(from_dt.strftime('%Y.%m.%d'), to_dt.strftime('%Y.%m.%d')))

    worksheet.write(0, 0, 'Дата')
    worksheet.write(0, 1, 'Фамилия Имя, табельный номер')
    worksheet.set_column(0, 1, 30)
    worksheet.write(0, 2, 'Время')
    worksheet.write(0, 3, 'Тип')

    records = list(AttendanceRecords.objects.select_related('user').filter(
        dttm__date__gte=from_dt,
        dttm__date__lte=to_dt,
        shop_id=shop_id,
    ).order_by('dttm', 'user'))

    prev_date = None
    prev_worker = None

    for index, record in enumerate(records):
        record_date = record.dttm.date()
        record_worker = record.user
        if prev_date != record_date:
            worksheet.write(index + 1, 0, record_date.strftime('%d.%m.%Y'))
            prev_date = record_date
        if prev_worker != record_worker:
            worksheet.write(index + 1, 1, '{} {}'.format(record_worker.last_name, record_worker.first_name))
            prev_worker = record_worker
        worksheet.write(index + 1, 2, record.dttm.strftime('%H:%M'))
        worksheet.write(index + 1, 3, AttendanceRecordsConverter.convert_type(record))

    return workbook, 'URV {}-{}'.format(from_dt.strftime('%Y.%m.%d'), to_dt.strftime('%Y.%m.%d'))


@api_method('GET', GetDepartmentListForm)
@xlsx_method
def get_department_stats_xlsx(request, workbook, form):
    """
    Скачивает статистику по магазинам за пред/текущий периоды

    Args:
        method: GET
        url: /api/download/get_supershops_stats
        pointer(int): указывает с айдишника какого магазина в querysete всех магазов будем инфу отдавать
        items_per_page(int): сколько шопов будем на фронте показывать
        title(str): required = False, название магазина
        super_shop_type(['H', 'C']): type of supershop
        region(str): title of region
        closed_before_dt(QOS_DATE): closed before this date
        opened_after_dt(QOS_DATE): opened after this date
        revenue_fot(str): range in format '123-345'
        revenue(str): range
        lack(str): range, percents
        fot(str): range
        idle(str): range, percents
        workers_amount(str): range
        sort_type(str): по какому параметру сортируем
        format(str): 'excel'/'raw'

    Returns:
        эксель файл с форматом Магазин | ФОТ/Выручка | ФОТ | Простой | Нехватка | Количество сотрудников
    """
    dt_now = date.today().replace(day=1)
    dt_prev = date.today().replace(day=1) - relativedelta(months=1)
    data, amount = get_shop_list_stats(form, request=request, display_format='excel')

    def write_stats(row_index, col_index, value_dict_name):
        worksheet.write(row_index, col_index, '{}/{} ({}%)'.format(
            round(shop_data[value_dict_name]['prev']),
            round(shop_data[value_dict_name]['curr']),
            round(shop_data[value_dict_name]['change']),
        ))

    worksheet = workbook.add_worksheet('Показатели по магазину')
    worksheet.set_column(0, 5, 20)
    worksheet.write(0, 0, 'Магазин')
    worksheet.write(0, 1, 'ФОТ/Выручка')
    worksheet.write(0, 2, 'ФОТ')
    worksheet.write(0, 3, 'Простой, %')
    worksheet.write(0, 4, 'Нехватка, %')
    worksheet.write(0, 5, 'Сотрудники')

    for index, shop_data in enumerate(data, start=1):
        worksheet.write(index, 0, '{}, {}'.format(shop_data['title'], shop_data['code'] or ''))
        write_stats(index, 1, 'fot_revenue')
        write_stats(index, 2, 'fot')
        write_stats(index, 3, 'idle')
        write_stats(index, 4, 'lack')
        write_stats(index, 5, 'workers_amount')

    return workbook, 'Shop Indicators({}-{}).xlsx'.format(dt_now.strftime('%B'), dt_prev.strftime('%B'))
