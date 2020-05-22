import pandas as pd
from rest_framework.response import Response
from src.forecast.models import (
    OperationType,
    PeriodClients,
)

from datetime import time, timedelta, datetime, date
from dateutil.relativedelta import relativedelta
from src.util.download import xlsx_method
from django.apps import apps
import json

from src.base.models import (
    Shop,
)
from src.timetable.models import (
    WorkType,
)

from django.db.models import Q
from src.base.exceptions import MessageError


def upload_demand_util(demand_file, shop_id, lang='ru'):
    try:
        df = pd.read_excel(demand_file)
    except KeyError:
        raise MessageError(code='xlsx_no_active_list', lang=lang)

    df = df[df.columns[:3]]
    #df['Время'] = pd.to_datetime(df['Время'])


    work_types = df['Тип работ'].unique()

    op_types = {
        op.work_type.work_type_name.name:op
        for op in OperationType.objects.select_related('work_type__work_type_name').filter(
            work_type__work_type_name__name__in=work_types,
        )
    }

    period_clients = []
    period_clients_to_delete_ids = []
    for work_type in work_types:
        operation_type = op_types.get(work_type)
        if not operation_type:
            raise MessageError(code='xlsx_undefined_work_type', lang=lang, params={'work_type': work_type})
        work_type_df = df[df['Тип работ'] == work_type]
        dttms = list(work_type_df['Время'])
        period_clients_to_delete_ids += list(PeriodClients.objects.filter(
            operation_type__work_type__shop_id=shop_id,
            operation_type__work_type__work_type_name__name=work_type,
            dttm_forecast__in=dttms,
            type=PeriodClients.LONG_FORECASE_TYPE,
        ).values_list('id', flat=True))
        period_clients += [
            PeriodClients(
                operation_type=op_types[work_type],
                value=data['Значение'],
                dttm_forecast=data['Время'],
                type=PeriodClients.LONG_FORECASE_TYPE,
            )
            for _, data in work_type_df.iterrows()
        ]
    
    PeriodClients.objects.filter(id__in=period_clients_to_delete_ids).delete()
    PeriodClients.objects.bulk_create(period_clients)

    return Response()

@xlsx_method
def download_demand_xlsx_util(request, workbook, form):
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
    from_dt = form['dt_from']
    to_dt = form['dt_to']

    shop = Shop.objects.get(id=form['shop_id'])
    timestep = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute  # minutes

    if (to_dt - from_dt).days > 90:
        raise MessageError(code='xlsx_long_period', lang=request.user.lang)

    worksheet = workbook.add_worksheet('{}-{}'.format(from_dt.strftime('%Y.%m.%d'), to_dt.strftime('%Y.%m.%d')))
    worksheet.set_column(0, 3, 30)
    worksheet.write(0, 0, 'Тип работ')
    worksheet.write(0, 1, 'Время')
    worksheet.write(0, 2, 'Значение(долгосрочный)')
    worksheet.write(0, 3, 'Значение(фактический)')


    period_demands = list(PeriodClients.objects.select_related(
        'operation_type__work_type', 
        'operation_type__operation_type_name',
        'operation_type__work_type__work_type_name',
    ).filter(
        operation_type__work_type__shop_id=form['shop_id'],
        dttm_forecast__date__gte=from_dt,
        dttm_forecast__date__lte=to_dt,
        type__in=[PeriodClients.FACT_TYPE, PeriodClients.LONG_FORECASE_TYPE]
    ).order_by('dttm_forecast', 'operation_type_id', 'type'))

    work_types = list(WorkType.objects.filter(shop_id=form['shop_id']).order_by('id'))
    operation_types = list(OperationType.objects.filter(work_type__in=work_types).select_related(
        'operation_type_name',
        'work_type',
        'work_type__work_type_name',
    ).order_by('id'))
    amount_operation_types = len(operation_types)

    dttm = datetime.combine(from_dt, time(0, 0))
    expected_record_amount = (to_dt - from_dt).days * amount_operation_types * 24 * 60 // timestep

    demand_index = 0
    period_demands_len = len(period_demands)
    if period_demands_len == 0:
        demand = PeriodClients()  # null model if no data

    for index in range(expected_record_amount):
        operation_type_index = index % amount_operation_types
        operation_type = operation_types[operation_type_index]
        work_type = operation_type.work_type

        # work_type_index = index % amount_work_types
        # work_type_name = work_types[work_type_index].name

        if period_demands_len > demand_index:
            demand = period_demands[demand_index]

        worksheet.write(index + 1, 0, work_type.work_type_name.name + ' ' + operation_type.operation_type_name.name)
        worksheet.write(index + 1, 1, dttm.strftime('%d.%m.%Y %H:%M:%S'))

        if (demand.dttm_forecast == dttm and
            demand.operation_type.work_type.work_type_name.name == work_type.work_type_name.name and
            demand.operation_type.operation_type_name.name == operation_type.operation_type_name.name):
            if demand.type == PeriodClients.FACT_TYPE:
                worksheet.write(index + 1, 3, round(demand.value, 1))
                demand_index += 1

                if index != expected_record_amount - 1:
                    next_demand = period_demands[demand_index]
                    if next_demand.type == PeriodClients.LONG_FORECASE_TYPE and \
                            next_demand.dttm_forecast == demand.dttm_forecast and \
                            next_demand.operation_type.work_type.work_type_name.name == demand.operation_type.work_type.work_type_name.name:
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

    return workbook, '{}-{}'.format(
        from_dt.strftime('%Y.%m.%d'),
        to_dt.strftime('%Y.%m.%d'),
    )

