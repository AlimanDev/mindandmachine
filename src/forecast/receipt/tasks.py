import json
import pandas as pd
from datetime import datetime, date, timedelta

from src.celery.celery import app
from src.base.models import Network
from src.forecast.models import OperationTypeName, OperationType, Receipt, PeriodClients



'''
Исходные данные хранятся в виде json в базе данных. как именно агреггировать network.settings_values['receive_data_info']
представлен в виде списка, каждый элемент состоит из:

{
        'update_gap': промежуток времени для обновления (сколько последних дней обновляем),
        'delete_gap': промежуток времени для хранения данных (сколько последних дней храним в базе данных),
        'grouping_period':  промежуток времени, по которому группировать значения,
        'aggregate': [
            {
                'timeserie_code': код операции,
                'timeserie_action': ['count', 'sum', 'nunique],
                'timeserie_value': какое значение для агрегации использовать,
                'timeserie_value_complex': опциональный вариант значения для группировки по нескольким полям,
                'timeserie_filters': словарь, например: {"ВидОперации": "Продажа"},
            },
            ...
        ],
        'shop_code_field_name': имя поля, где искать код магазина,
        'receipt_code_field_name': имя поля, где искать receipt code (uuid),
        'dttm_field_name': имя поля, где искать дату и время события,
        'data_type': тип данных
}
'''


@app.task
def aggregate_timeserie_value():
    """
    Потенциально для любого вида значений, которые нужно агрегировать в timeserie
    конкретно сейчас для агрегации чеков

    Исходные данные хранятся в виде json в базе данных. как именно агреггировать network.settings_values['receive_data_info']
    представлен в виде списка, каждый элемент состоит из:

    :return:
    """

    dttm_now = datetime.now()

    for network in Network.objects.all():
        network.settings_values = json.loads(network.settings_values)
        receive_data_info = network.settings_values.get('receive_data_info', '')

        if receive_data_info:
            for timeserie in receive_data_info:
                grouping_period = timeserie.get('grouping_period', 'h1')
                update_gap = timeserie.get('update_gap', 3)
                data_type = timeserie.get('data_type')
                for aggregate in timeserie['aggregate']:
                    aggr_filters = aggregate.get('timeserie_filters')
                    timeserie_action = aggregate.get('timeserie_action', 'sum')

                    # check all needed
                    if not (aggregate.get('timeserie_code') and (
                            aggregate.get('timeserie_value') or aggregate.get('timeserie_value_complex'))):
                        raise Exception(f"no needed values in timeserie: {timeserie}. Network: {network}")

                    print(network, aggregate['timeserie_code'])
                    operation_type_name = OperationTypeName.objects.get(
                        network=network,
                        code=aggregate['timeserie_code'],
                    )

                    # по выборке всех типов очень много может быть, поэтому цикл по магазинам:
                    operations_type = OperationType.objects.filter(
                        shop__network=network,
                        operation_type_name=operation_type_name,
                    ).exclude(
                        dttm_deleted__lte=dttm_now,
                        shop__dttm_deleted__lte=dttm_now,
                    ).select_related('shop')

                    for operation_type in operations_type:
                        for dt in (date.today() - timedelta(days=i) for i in range(update_gap+1)):
                            # Большое кол-во чеков занимают слишком много ОЗУ, обрабатываем по одному дню
                            items_list = []
                            items = Receipt.objects.filter(
                                shop=operation_type.shop, dt=dt, data_type=data_type)
                            for item in items:
                                item.info = json.loads(item.info)

                                # Пропускаем записи, которые не удовл. значениям в фильтре
                                if aggr_filters and not all(item.info.get(k) == v for k, v in aggr_filters.items()):
                                    continue

                                value = 0
                                if 'timeserie_value' in aggregate:
                                    value = item.info.get(aggregate['timeserie_value'], 0)  # fixme: то ли ошибку лучше кидать, то ли пропускать (0 ставить)
                                    if isinstance(value, str):
                                        value = value.replace(',', '.')
                                    value = float(value)
                                elif 'timeserie_value_complex' in aggregate:
                                    value = '_'.join(item.info.get(field_name) for field_name in aggregate['timeserie_value_complex'])
                                items_list.append({
                                    'dttm': item.dttm,
                                    'value': value,
                                })

                            item_df = pd.DataFrame(items_list, columns=['dttm', 'value'])

                            if grouping_period == 'h1':
                                # todo: вообще в item_df могут быть значения за какие-то периоды, но не за все. Когда нет, то по хорошему
                                # надо ставить 0. Ноооо, скорей всего в этом случае (когда событий мало) нулевые периоды плохо будут
                                # влиять на модель прогноза (если нет события, то риск ошибиться большой).

                                item_df['dttm'] = item_df['dttm'].apply(lambda x: x.replace(minute=0, second=0, microsecond=0))
                            elif grouping_period == 'd1':
                                item_df['dttm'] = item_df['dttm'].apply(lambda x: x.replace(hour=0, minute=0, second=0, microsecond=0))
                                item_df = pd.merge(
                                    pd.DataFrame([dt], columns=['dttm']).astype('datetime64[ns]'),
                                    item_df,
                                    on='dttm',
                                    how='left',
                                )
                                item_df = item_df.fillna(0)  # пропущенные дни вставляем (в какие то дни что то могут не делать)
                            else:
                                # todo: добавить варианты, когда группируем не по часам.
                                raise NotImplementedError(f'grouping {grouping_period}, timeserie {timeserie}, network {network}')

                            periods_data = item_df.groupby('dttm')['value']
                            if timeserie_action == 'sum':
                                periods_data = periods_data.sum()
                            elif timeserie_action == 'count':
                                periods_data = periods_data.count()
                            elif timeserie_action == 'nunique':
                                periods_data = periods_data.nunique()
                            else:
                                raise NotImplementedError(f'timeserie_action {timeserie_action}, timeserie {timeserie}, network {network}')

                            periods_data = periods_data.reset_index()
                            PeriodClients.objects.filter(
                                operation_type=operation_type,
                                dt_report=dt,
                                type=PeriodClients.FACT_TYPE,
                            ).delete()

                            PeriodClients.objects.bulk_create([
                                PeriodClients(
                                    operation_type=operation_type,
                                    dttm_forecast=period['dttm'],
                                    dt_report=dt,
                                    value=period['value'],
                                    type=PeriodClients.FACT_TYPE,
                                ) for _, period in periods_data.iterrows()
                            ])


@app.task
def clean_timeserie_actions():
    dttm_now = datetime.now()

    for network in Network.objects.all():
        network.settings_values = json.loads(network.settings_values)
        receive_data_info = network.settings_values.get('receive_data_info', '')

        if receive_data_info:
            for timeserie in receive_data_info:
                delete_gap = timeserie.get('delete_gap', 31)
                data_type = timeserie.get('data_type')
                dttm_for_delete = (datetime.now() - timedelta(days=delete_gap)).replace(hour=0, minute=0, second=0)

                for aggregate in timeserie['aggregate']:
                    print(network, aggregate['timeserie_code'])
                    operation_type_name = OperationTypeName.objects.get(
                        network=network,
                        code=aggregate['timeserie_code'],
                    )

                    operations_type = OperationType.objects.filter(
                        shop__network=network,
                        operation_type_name=operation_type_name,
                    ).exclude(
                        dttm_deleted__lte=dttm_now,
                        shop__dttm_deleted__lte=dttm_now,
                    ).select_related('shop')
                    for operation_type in operations_type:
                        Receipt.objects.filter(shop=operation_type.shop, dttm__lt=dttm_for_delete, data_type=data_type).delete()
