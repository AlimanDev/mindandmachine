import pandas as pd
import numpy as np
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
            raise ValidationError(_('There is no such work type or it is not associated with the operation type {work_type}.').format(work_type=work_type))
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
            for _not_used, data in work_type_df.iterrows()
        ]
    
    PeriodClients.objects.filter(id__in=period_clients_to_delete_ids).delete()
    PeriodClients.objects.bulk_create(period_clients)

    return Response()


def upload_demand_util_v2(new_workload, shop_id, type=PeriodClients.LONG_FORECASE_TYPE):
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
    for operation_type in set(new_workload.columns) - {'dttm'}:
        operation = op_types.get(operation_type)
        if not operation:
            raise ValidationError(_('There is no such operation type {operation_type}.').format(operation_type=operation_type))
        period_clients.extend(
            [
                PeriodClients(
                    dttm_forecast=row['dttm'],
                    operation_type=operation,
                    type=type,
                    value=row[operation_type]

                ) for _not_used, row in new_workload[['dttm', operation_type]].iterrows()
            ]
        )
    PeriodClients.objects.filter(
        dttm_forecast__gte=dttm_min,
        dttm_forecast__lte=dttm_max,
        operation_type__in=op_types.values(),
        type=type,
    ).delete()
    PeriodClients.objects.bulk_create(period_clients)
    return Response()


def upload_demand(demand_file, shop_id=None, type=PeriodClients.LONG_FORECASE_TYPE):
    try:
        df = pd.read_excel(demand_file, dtype=str)
    except:
        try:
            df = pd.read_csv(demand_file, dtype=str)
        except:
            raise ValidationError(_("Files with this extension are not supported."))
    with transaction.atomic():
        operation_types = list(set(df.columns) - {'dttm', 'shop_code'})
        df[operation_types] = df[operation_types].astype(float)
        df.loc[:, 'dttm'] = pd.to_datetime(df.dttm)
        if 'shop_code' in df.columns:
            shops = Shop.objects.filter(code__in=df.shop_code.unique())
            for s in shops:
                upload_demand_util_v2(df.loc[df.shop_code==s.code, set(df.columns) - {'shop_code'}], s.id, type)
        else:
            if not shop_id:
                raise ValidationError(_("Shop id should be defined"))

            upload_demand_util_v2(df, shop_id, type)
    
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
    df[DTTM_COL] = pd.to_datetime(df[DTTM_COL])
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
        return upload_demand_util_v2(df, shop_id)
    
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

    TYPES = {
        'F': "Фактическая",
        'L': "Прогнозируемая",
    }

    shop = Shop.objects.get(id=form['shop_id'])
    timestep = pd.DateOffset(hours=shop.forecast_step_minutes.hour, minutes=shop.forecast_step_minutes.minute, seconds=shop.forecast_step_minutes.second)


    # TODO: нужно ли это ограничение?
    if (to_dt - from_dt).days > 90:
        raise ValidationError(_('Please select a period of no more than 90 days.'))
    
    sheet_name = '{}-{}'.format(from_dt.strftime('%Y.%m.%d'), to_dt.strftime('%Y.%m.%d'))
    operation_types = OperationType.objects.filter(shop=shop).select_related('operation_type_name')
    if 'operation_type_name_ids' in form:
        operation_types = operation_types.filter(operation_type_name_id__in=form['operation_type_name_ids'])
    
    if 'operation_type_ids' in form:
        operation_types = operation_types.filter(id__in=form['operation_type_ids'])
    
    dttms = pd.date_range(from_dt, datetime.combine(to_dt, time(23, 59)), freq=timestep)

    df = pd.DataFrame(data=dttms, columns=['dttm']).set_index('dttm')
    
    for operation_type in operation_types:
        demand_data = list(
            PeriodClients.objects.filter(
                operation_type=operation_type,
                dttm_forecast__date__gte=from_dt,
                dttm_forecast__date__lte=to_dt,
                type=form['type'],
            ).order_by('dttm_forecast').values_list(
                'value',
                'dttm_forecast',
            )
        )
        if not demand_data:
            demand_data = [(np.nan, dttms[0])]
        demand_df = pd.DataFrame(data=demand_data, columns=[operation_type.operation_type_name.name, 'dttm']).set_index('dttm')
        df = df.merge(demand_df, how='left', left_index=True, right_index=True)

    if df.count().any():
        df = df.dropna(how='all')
    df.fillna(0, inplace=True)
    
    df.to_excel(workbook, sheet_name=sheet_name)
    worksheet = workbook.sheets[sheet_name]
    header_format = workbook.book.add_format(dict(border=1, align='center', valign='vcenter', text_wrap=True, bold=True))
    value_format = workbook.book.add_format(dict(align='right'))
    for i, o_type in enumerate(operation_types):
        worksheet.write_string(0, i + 1, o_type.operation_type_name.name, header_format)
        worksheet.set_column(i + 1, i + 1, len(o_type.operation_type_name.name) + 1, value_format)
    worksheet.set_column(0, 0, 21, workbook.book.add_format(dict(align='center', valign='vcenter', text_wrap=True, bold=True)))
    
    return workbook, '{} нагрузка для {} за {}-{}'.format(
        TYPES[form['type']],
        shop.name,
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
            error_code = ''
            if period_demand_value.get('timeserie_code', False):
                operation_type = operation_codes.get(period_demand_value.get('timeserie_code'))
                error_code = f"code {period_demand_value.get('timeserie_code')}"
            elif period_demand_value.get('timeserie_name', False):
                operation_type = operation_names.get(period_demand_value.get('timeserie_name'))
                error_code = f"name_id {period_demand_value.get('timeserie_name')}"
            elif period_demand_value.get('timeserie_id', False):
                operation_type = operation_ids.get(period_demand_value.get('timeserie_id'))
                error_code = f"id {period_demand_value.get('timeserie_id')}"

            if not operation_type:
                raise ValidationError(f"Operation type with {error_code} does not exist in shop {shop.name}")
            
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
