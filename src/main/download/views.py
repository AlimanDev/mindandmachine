from src.util.utils import api_method
from .utils import xlsx_method
from .forms import (
    GetTable,
    GetDemandXlsxForm,
    GetUrvXlsxForm,
)
from src.db.models import (
    Shop,
    User,
    WorkerDay,
    PeriodClients,
    CashboxType,
    AttendanceRecords,
)
from datetime import time, timedelta, datetime
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

    shop = Shop.objects.get(id=FormUtil.get_shop_id(request, form))
    checkpoint = FormUtil.get_checkpoint(form)

    tabel = Tabel_xlsx(
        workbook,
        shop,
        form['weekday'],
        worksheet=ws,
        prod_days=None
    )
    users = list(User.objects.qos_filter_active(
        dt_from=tabel.prod_days[-1].dt,
        dt_to=tabel.prod_days[0].dt,
        shop=shop,
    ).select_related('position').order_by('position_id', 'last_name', 'first_name', 'tabel_code'))

    breaktimes = json.loads(shop.break_triplets)
    breaktimes = list(map(lambda x: (x[0] / 60, x[1] / 60, sum(x[2]) / 60), breaktimes))

    workdays = WorkerDay.objects.qos_filter_version(checkpoint).select_related('worker').filter(
        worker__shop=shop,
        dt__gte=tabel.prod_days[0].dt,
        dt__lte=tabel.prod_days[-1].dt,
    ).order_by('worker__position_id', 'worker__last_name', 'worker__first_name', 'worker__tabel_code', 'dt')

    tabel.format_cells(len(users))
    tabel.add_main_info()

    # construct day
    tabel.construct_dates('%d', 12, 6, int)

    # construct weekday
    tabel.construct_dates('%w', 14, 6)

    #construct day 2
    tabel.construct_dates('d%d', 15, 6)

    tabel.construnts_users_info(users, 16, 0, ['code', 'fio', 'position', 'hired'])

    tabel.fill_table(workdays, users, breaktimes, 16, 6)

    tabel.add_xlsx_functions(len(users), 12, 37)
    tabel.add_sign(16 + len(users) + 2)

    return workbook, 'Tabel'


@api_method(
    'GET',
    GetDemandXlsxForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
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
        demand_model(char): !! attention !! передавать что-то из clients/queue/products (см. окончание моделей Period..)

    Returns:
        эксель файл с форматом Тип работ | Время | Значение
    """
    from_dt = form['from_dt']
    to_dt = form['to_dt']
    timestep = 30  # minutes

    if (to_dt - from_dt).days > 90:
        return JsonResponse.internal_error('Выберите, пожалуйста, более короткий период.'), 'error'

    worksheet = workbook.add_worksheet('{}-{}'.format(from_dt.strftime('%Y.%m.%d'), to_dt.strftime('%Y.%m.%d')))
    worksheet.set_column(0, 3, 30)
    worksheet.write(0, 0, 'Тип работ')
    worksheet.write(0, 1, 'Время')
    worksheet.write(0, 2, 'Значение(долгосрочный)')
    worksheet.write(0, 3, 'Значение(фактический)')

    try:
        model = apps.get_model('db', 'period{}'.format(form['demand_model']))
    except LookupError:
        return JsonResponse.internal_error('incorrect demand model'), 'error'

    period_demands = list(model.objects.select_related('cashbox_type').filter(
        cashbox_type__shop_id=form['shop_id'],
        dttm_forecast__date__gte=from_dt,
        dttm_forecast__date__lte=to_dt,
        type__in=[PeriodClients.FACT_TYPE, PeriodClients.LONG_FORECASE_TYPE]
    ).order_by('dttm_forecast', 'cashbox_type_id', 'type'))

    cashbox_types = list(CashboxType.objects.filter(shop_id=form['shop_id']).order_by('id'))
    amount_cashbox_types = len(cashbox_types)

    dttm = datetime.combine(from_dt, time(0, 0))
    expected_record_amount = (to_dt - from_dt).days * amount_cashbox_types * 24 * 60 // timestep

    demand_index = 0
    period_demands_len = len(period_demands)
    if period_demands_len == 0:
        demand = PeriodClients()  # null model if no data

    for index in range(expected_record_amount):
        cashbox_type_index = index % amount_cashbox_types
        cashbox_type_name = cashbox_types[cashbox_type_index].name

        if period_demands_len > demand_index:
            demand = period_demands[demand_index]

        worksheet.write(index + 1, 0, cashbox_type_name)
        worksheet.write(index + 1, 1, dttm.strftime('%d.%m.%Y %H:%M:%S'))

        if demand.dttm_forecast == dttm and demand.cashbox_type.name == cashbox_type_name:
            if demand.type == PeriodClients.FACT_TYPE:
                worksheet.write(index + 1, 3, round(demand.value, 1))
                demand_index += 1

                if index != expected_record_amount - 1:
                    next_demand = period_demands[demand_index]
                    if next_demand.type == PeriodClients.LONG_FORECASE_TYPE and\
                        next_demand.dttm_forecast == demand.dttm_forecast and\
                            next_demand.cashbox_type.name == demand.cashbox_type.name:
                                worksheet.write(index + 1, 2, round(next_demand.value, 1))
                                demand_index += 1
            else:
                worksheet.write(index + 1, 2, round(demand.value, 1))
                worksheet.write(index + 1, 3, 'Нет данных')
                demand_index += 1

        else:
            worksheet.write(index + 1, 2, 'Нет данных')
            worksheet.write(index + 1, 3, 'Нет данных')
        if index % amount_cashbox_types == amount_cashbox_types - 1 and index != 0:
            dttm += timedelta(minutes=timestep)

    return workbook, '{} {}-{}'.format(model.__name__, from_dt.strftime('%Y.%m.%d'), to_dt.strftime('%Y.%m.%d'))


@api_method(
    'GET',
    GetUrvXlsxForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
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

    records = list(AttendanceRecords.objects.select_related('identifier', 'identifier__worker').filter(
        dttm__date__gte=from_dt,
        dttm__date__lte=to_dt,
        identifier__worker__shop_id=shop_id,
    ).order_by('dttm', 'identifier__worker'))

    prev_date = None
    prev_worker = None

    for index, record in enumerate(records):
        record_date = record.dttm.date()
        record_worker = record.identifier.worker
        if prev_date != record_date:
            worksheet.write(index + 1, 0, record_date.strftime('%d.%m.%Y'))
            prev_date = record_date
        if prev_worker != record_worker:
            worksheet.write(index + 1, 1, '{} {}'.format(record_worker.last_name, record_worker.first_name))
            prev_worker = record_worker
        worksheet.write(index + 1, 2, record.dttm.strftime('%H:%M'))
        worksheet.write(index + 1, 3, AttendanceRecordsConverter.convert_type(record))

    return workbook, 'URV {}-{}'.format(from_dt.strftime('%Y.%m.%d'), to_dt.strftime('%Y.%m.%d'))
