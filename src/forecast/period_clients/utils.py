import pandas as pd
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from src.forecast.models import (
    OperationType,
    PeriodClients,
    OperationTypeName,
)

from datetime import time, timedelta, datetime, date
from dateutil.relativedelta import relativedelta
from src.util.download import xlsx_method
from django.apps import apps
import json
from django.db import transaction
from django.utils.translation import gettext as _
from src.base.models import (
    Shop,
)
from src.timetable.models import (
    WorkType,
)

from django.db.models import Q
from src.util.models_converter import Converter

def upload_demand_util_v1(df, shop_id, lang):
    df = df[df.columns[:3]]

    work_types = df['Тип работ'].unique()

    op_types = {
        op.operation_type_name.name:op
        for op in OperationType.objects.select_related('operation_type_name').filter(
            operation_type_name__name__in=work_types,
            shop_id=shop_id,
        )
    }

    period_clients = []
    period_clients_to_delete_ids = []
    for work_type in work_types:
        operation_type = op_types.get(work_type)
        if not operation_type:
            raise ValidationError(_('There is no such work type or it is not associated with the operation type {work_type}.').format(work_type=worktype))
        work_type_df = df[df['Тип работ'] == work_type]
        dttms = list(work_type_df['Время'])
        period_clients_to_delete_ids += list(PeriodClients.objects.filter(
            operation_type__shop_id=shop_id,
            operation_type__operation_type_name__name=work_type,
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


def upload_demand_util_v2(new_workload, shop_id, lang):
    dttm_min = new_workload.dttm.min()
    dttm_max = new_workload.dttm.max()
    op_types = {
        op.operation_type_name.name:op
        for op in OperationType.objects.select_related('operation_type_name').filter(
            operation_type_name__name__in=set(new_workload.columns) - {'dttm'},
            shop_id=shop_id,
        )
    }
    period_clients = []
    for worktype in set(new_workload.columns) - {'dttm'}:
        operation = op_types.get(worktype)
        if not operation:
            raise ValidationError(_('There is no such work type or it is not associated with the operation type {work_type}.').format(work_type=worktype))
        period_clients += [
            PeriodClients(
                dttm_forecast=row['dttm'],
                operation_type=operation,
                type=PeriodClients.LONG_FORECASE_TYPE,
                value=row[worktype]

            ) for _, row in new_workload[['dttm', worktype]].iterrows()
        ]
    PeriodClients.objects.filter(
        dttm_forecast__gte=dttm_min,
        dttm_forecast__lte=dttm_max,
        operation_type__in=op_types.values(),
        type=PeriodClients.LONG_FORECASE_TYPE
    ).delete()
    PeriodClients.objects.bulk_create(period_clients)
    return Response()

def upload_demand_util_v3(operation_type_name, demand_file, index_col=None, type='F'):
    if index_col:
        df = pd.read_excel(demand_file, index_col=index_col, dtype=str)
    else:
        df = pd.read_excel(demand_file, dtype=str)
    SHOP_COL = df.columns[0]
    DTTM_COL = df.columns[1]
    VALUE_COL = df.columns[2]
    df[VALUE_COL] = df[VALUE_COL].astype(float)
    df[DTTM_COL] = pd.to_datetime(df[VALUE_COL])
    with transaction.atomic():
        shops = df[SHOP_COL].unique()
        shops = Shop.objects.filter(code__in=shops)
        operation_types = {ot.shop_id: ot for ot in OperationType.objects.filter(shop__in=shops, operation_type_name=operation_type_name)}
        creates = []
        for s in shops:
            data = df[df[SHOP_COL] == s.code]
            min_dttm = min(data[DTTM_COL])
            max_dttm = max(data[DTTM_COL])
            PeriodClients.objects.filter(operation_type=operation_types[s.id], dttm_forecast__gte=min_dttm, dttm_forecast__lte=max_dttm, type=type).delete()
            creates.append(
                (
                    s.code, 
                    len(
                        PeriodClients.objects.bulk_create(
                            [
                                PeriodClients(
                                    operation_type=operation_types[s.id],
                                    dttm_forecast=row[DTTM_COL],
                                    value=row[VALUE_COL],
                                    type=type,
                                )
                                for _, row in data.iterrows()
                            ]
                        )
                    )
                )
            )
    return Response(creates)


def upload_demand_util(demand_file, shop_id, lang='ru'):
    try:
        df = pd.read_excel(demand_file)
    except KeyError:
        raise ValidationError(_('Failed to open active sheet.'))

    if 'dttm' in df.columns:
        return upload_demand_util_v2(df, shop_id, lang)
    
    return upload_demand_util_v1(df, shop_id, lang)


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
        raise ValidationError(_('Please select a period of no more than 90 days.'))

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


def create_demand(data):
    '''
    Функция для внесения значений операций.
    :param 
        data JSON
        {
            'shop_id': 1, || 'shop_code': 'shop'
            'dt_from': '2020-07-01', || datetime.date(2020, 7, 1)
            'dt_to': '2020-07-31', || datetime.date(2020, 7, 31)
            'type': 'F', || 'L'
            'serie': [
                {
                    'dttm': '2020-07-01T08:00:00',
                    'timeserie_id': 1, || 'timeserie_code': 'bills'
                    'value': 2.0,
                },
                ...
                {
                    'dttm': '2020-07-31T22:00:00',
                    'timeserie_id': 1, || 'timeserie_code': 'bills'
                    'value': 3.0,
                }
            ]
        }
    '''
    def parse_datetime(value):
        value['dttm'] = Converter.parse_datetime(value.get('dttm'))
        return value

    models_list = []

    shop_id = data.get('shop_id')
    if not shop_id:
        shop = Shop.objects.get(code=data.get('shop_code'))
    else:
        shop = Shop.objects.get(id=shop_id)
    
    dt_from = Converter.parse_date(data['dt_from']) if type(data['dt_from']) is str else data['dt_from']
    dt_to = Converter.parse_date(data['dt_to']) if type(data['dt_to']) is str else data['dt_to']
    forecase_type = data.get('type', PeriodClients.LONG_FORECASE_TYPE)
    operation_types = list(OperationType.objects.select_related('operation_type_name').filter(Q(shop_id=shop.id) | Q(work_type__shop_id=shop.id)))
    operation_codes = {
        ot.operation_type_name.code: ot
        for ot in operation_types
    }
    operation_ids = {
        ot.id: ot
        for ot in operation_types
    }
    operation_names = {
        ot.operation_type_name_id: ot
        for ot in operation_types
    }
    if data['serie'][0].get('timeserie_code', False):
        operation_types_to_delete = set([ operation_codes.get(x.get('timeserie_code')) for x in data['serie']])
    elif data['serie'][0].get('timeserie_name', False):
        operation_types_to_delete = set([ operation_names.get(x.get('timeserie_name')) for x in data['serie']])
    else:
        operation_types_to_delete = set([ operation_ids.get(x.get('timeserie_id')) for x in data['serie']])
    
    data['serie'] = list(map(parse_datetime, data['serie']))

    min_time = time(23)
    max_time = time(0)

    for serie in data['serie']:
        if serie['dttm'].time() > max_time:
            max_time = serie['dttm'].time()

        if serie['dttm'].time() < min_time:
            min_time = serie['dttm'].time()

    with transaction.atomic():
        PeriodClients.objects.filter(
            Q(operation_type__shop_id=shop.id) | Q(operation_type__work_type__shop_id=shop.id),
            type=forecase_type,
            dttm_forecast__date__gte=dt_from,
            dttm_forecast__date__lte=dt_to,
            dttm_forecast__time__gte=min_time,
            dttm_forecast__time__lte=max_time,
            operation_type__in=operation_types_to_delete,
        ).delete()

        for period_demand_value in data['serie']:
            clients = period_demand_value['value']
            clients = 0 if clients < 0 else clients
            operation_type = None
            if period_demand_value.get('timeserie_code', False):
                operation_type = operation_codes.get(period_demand_value.get('timeserie_code'))
            elif period_demand_value.get('timeserie_name', False):
                operation_type = operation_names.get(period_demand_value.get('timeserie_name'))
            elif period_demand_value.get('timeserie_id', False):
                operation_type = operation_ids.get(period_demand_value.get('timeserie_id'))
            models_list.append(
                PeriodClients(
                    type=forecase_type,
                    dttm_forecast=period_demand_value.get('dttm'),
                    operation_type=operation_type,
                    value=clients,
                )
            )
        PeriodClients.objects.bulk_create(models_list)
    return True
