import logging
from datetime import time, datetime
from dateutil.parser import ParserError

import pandas as pd
import numpy as np
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext as _
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from src.base.models import Shop
from src.forecast.models import OperationType, PeriodClients
from src.util.download import xlsx_method
from src.util.models_converter import Converter

logger = logging.getLogger('upload_demand')

def upload_demand(demand_file, shop_id: int = None, type: str = PeriodClients.LONG_FORECASE_TYPE) -> list[str]:
    """
    Upload demand from excel/csv to PeriodClients (instead of aggregating Receipts). Columns should map to OperationTypeNames.
    `shop_code`s are taken from file or `shop_id` is used. The latter case will raise ValidationError if shop wasn't found.
    Errors are collected and returned. Bad rows/shops will be skipped.
    """
    try:
        df = pd.read_excel(demand_file, dtype=str)
    except:
        try:
            df = pd.read_csv(demand_file, dtype=str)
        except:
            raise ValidationError(_('Files with this extension are not supported.'))
    operation_types = list(set(df.columns) - {'dttm', 'shop_code'})

    # Data validation and conversion
    try:
        df.loc[:, 'dttm'] = pd.to_datetime(df.dttm).dt.round('s')
    except ParserError as e:
        raise ValidationError(_('Incorrect datetime: {}').format(e.args[1]))
    try:
        df[operation_types] = df[operation_types].astype(float)
    except ValueError as e:
        raise ValidationError(_('Incorrect operation value: {}').format(e.args[0].split(":")[1]))

    errors = []
    if 'shop_code' in df.columns:
        # Using shop_codes from file
        for code in df.shop_code.unique():
            if pd.isna(code):
                errors.append(_('Empty shop code ignored'))
                continue
            try:
                shop = Shop.objects.get(code=code)
            except Shop.DoesNotExist:
                errors.append(_('Shop with code {} not found').format(code))
                continue
            except Shop.MultipleObjectsReturned:
                shops_names = Shop.objects.filter(code=code).values_list('name', flat=True)
                errors.append(_('Multiple shops with code {} found: {}. Shops must have unique codes.').format(code, ', '.join(shops_names)))
                continue

            try:
                errors += upload_demand_util_v2(df.loc[df.shop_code==code, set(df.columns) - {'shop_code'}], shop, type)
            except Exception as e:
                logger.exception(f'Unexpected error for shop {shop.name}: {str(e)}')
                errors.append(_('Unexpected error for shop {}, please contact Technical support').format(shop.name))

    elif shop_id:
        # If no shop_code column, then use shop_id
        try:
            shop = Shop.objects.get(id=shop_id)
        except Shop.DoesNotExist:
            raise ValidationError(_('Shop with code {} not found').format(code))

        try:
            errors += upload_demand_util_v2(df, shop, type)
        except Exception as e:
            logger.exception(f'Unexpected error for shop {shop.name}: {str(e)}')
            errors.append(_('Unexpected error for shop {}, please contact Technical support').format(shop.name))

    else:
        raise ValidationError(_('Shop id should be defined'))

    return errors


def upload_demand_util_v2(new_workload, shop: Shop, type=PeriodClients.LONG_FORECASE_TYPE) -> list[str]:
    """
    Save PeriodClients for each OperationType found for the shop. Delete previous ones.
    Errors are collected and returned.
    """
    errors = set()
    new_workload.dttm = new_workload.dttm.dt.round('s')
    dttm_min = new_workload.dttm.min()
    dttm_max = new_workload.dttm.max()
    op_types = {
        op.operation_type_name.name: op
        for op in OperationType.objects.select_related('operation_type_name').filter(
            operation_type_name__name__in=set(new_workload.columns) - {'dttm'},
            shop=shop,
        )
    }
    period_clients = []
    for operation_type in set(new_workload.columns) - {'dttm'}:
        operation = op_types.get(operation_type)
        if not operation:
            errors.add(_('No operation type {} for shop {}').format(operation_type, shop.name))
            continue

        for i, row in new_workload[['dttm', operation_type]].iterrows():
            if pd.isnull(row['dttm']):
                errors.add(_('No datetime on row {}').format(i+2))   # 1 for headers, 1 for indexing from 0
                continue
            if pd.isnull(row[operation_type]):
                errors.add(_('No value on row {} for operation type {}').format(i+2, operation_type))
                continue
            period_clients.append(PeriodClients(
                dttm_forecast=row['dttm'],
                dt_report=row['dttm'].date(),
                operation_type=operation,
                type=type,
                value=row[operation_type]
            ))

    with transaction.atomic():
        PeriodClients.objects.filter(
            dttm_forecast__gte=dttm_min,
            dttm_forecast__lte=dttm_max,
            operation_type__in=op_types.values(),
            type=type,
        ).delete()
        PeriodClients.objects.bulk_create(period_clients)
    return list(errors)


def upload_demand_util_v3(operation_type_name, demand_file, index_col=None, type='F'):
        # See src.forecast.period_clients.views.PeriodClientsViewSet.upload_demand. Potentially needs to be removed.
    if index_col:
        df = pd.read_excel(demand_file, index_col=index_col, dtype=str)
    else:
        df = pd.read_excel(demand_file, dtype=str)
    SHOP_COL = df.columns[0]
    DTTM_COL = df.columns[1]
    VALUE_COL = df.columns[2]
    df[VALUE_COL] = df[VALUE_COL].astype(float)
    df[DTTM_COL] = pd.to_datetime(df[DTTM_COL]).dt.round('s')
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
                                    dt_report=row[DTTM_COL].date(),
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
                    dt_report=period_demand_value.get('dttm').date(),
                    operation_type=operation_type,
                    value=clients,
                )
            )
        PeriodClients.objects.bulk_create(models_list)
    return True
