from datetime import timedelta, datetime

from src.base.models import (
    Shop,
    Network,
)
from src.forecast.models import (
    PeriodClients,
    Receipt,
    OperationType,
    OperationTypeName
)
import pandas as pd
from src.celery.celery import app
import json


# todo: нужно добавить тип Receipts (объектов)
'''
Исходные данные хранятся в виде json в базе данных. как именно агреггировать network.settings_values['receive_data_info']
представлен в виде списка, каждый элемент состоит из:

{
        # 'timeserie_shop_code':  код магазина,
        'update_gap': промежуток времени для обновления (сколько последних дней обновляем),
        'delete_gap': промежуток времени для хранения данных (сколько последних дней храним в базе данных),
        'timeserie_code': код операции,
        'timeserie_action': ['count', 'sum']
        'timeserie_value': какое значение для агрегации использовать,
        'grouping_period':  промежуток времени, по которому группировать значения,
        # 'timeserie_filters': словарь какие поля, какие значения должны иметь, # todo: круто бы добавить
        # 'timeserie_dttm':
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
                timeserie_action = timeserie.get('timeserie_action', 'sum')
                update_gap = timeserie.get('update_gap', 3)
                dttm_for_update = (datetime.now() - timedelta(days=update_gap)).replace(hour=0, minute=0, second=0)


                # check all needed
                if not (timeserie.get('timeserie_code') and timeserie.get('timeserie_value')):
                    raise Exception(f"no needed values in timeserie: {timeserie}. Network: {network}")

                print(network, timeserie['timeserie_code'])
                operation_type_name = OperationTypeName.objects.get(network=network, code=timeserie['timeserie_code'])

                # по выборке всех типов очень много может быть, поэтому цикл по магазинам:

                operations_type = OperationType.objects.filter(
                    shop__network=network,
                    operation_type_name=operation_type_name,
                ).exclude(
                    dttm_deleted__lte=dttm_now,
                    shop__dttm_deleted__lte=dttm_now,
                ).select_related('shop')

                for operation_type in operations_type:
                    items_list = []
                    items = Receipt.objects.filter(shop=operation_type.shop, dttm__gte=dttm_for_update)
                    for item in items:
                        item.info = json.loads(item.info)
                        items_list.append({
                            'dttm': item.dttm,
                            'value': float(item.info.get(timeserie['timeserie_value'], 0))  # fixme: то ли ошибку лучше кидать, то ли пропускать (0 ставить)
                        })

                    item_df = pd.DataFrame(items_list, columns=['dttm', 'value'])
                    dates = pd.date_range(dttm_for_update.date(), dttm_now.date())  # item_df.dttm.dt.date.unique()

                    if grouping_period == 'h1':
                        # todo: вообще в item_df могут быть значения за какие-то периоды, но не за все. Когда нет, то по хорошему
                        # надо ставить 0. Ноооо, скорей всего в этом случае (когда событий мало) нулевые периоды плохо будут
                        # влиять на модель прогноза (если нет события, то риск ошибиться большой).

                        item_df['dttm'] = item_df['dttm'].apply(lambda x: x.replace(minute=0, second=0, microsecond=0))
                    elif grouping_period == 'd1':
                        item_df['dttm'] = item_df['dttm'].apply(lambda x: x.replace(hour=0, minute=0, second=0, microsecond=0))
                        item_df = pd.merge(
                            pd.DataFrame(dates, columns=['dttm']),
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
                    else:
                        raise NotImplementedError(f'timeserie_action {timeserie_action}, timeserie {timeserie}, network {network}')

                    periods_data = periods_data.reset_index()
                    PeriodClients.objects.filter(
                        operation_type=operation_type,
                        dttm_forecast__date__in=dates,
                        type=PeriodClients.FACT_TYPE,
                    ).delete()

                    PeriodClients.objects.bulk_create([
                        PeriodClients(
                            operation_type=operation_type,
                            dttm_forecast=period['dttm'],
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
                dttm_for_delete = (datetime.now() - timedelta(days=delete_gap)).replace(hour=0, minute=0, second=0)

                print(network, timeserie['timeserie_code'])
                operation_type_name = OperationTypeName.objects.get(network=network, code=timeserie['timeserie_code'])

                operations_type = OperationType.objects.filter(
                    shop__network=network,
                    operation_type_name=operation_type_name,
                ).exclude(
                    dttm_deleted__lte=dttm_now,
                    shop__dttm_deleted__lte=dttm_now,
                ).select_related('shop')
                for operation_type in operations_type:
                    Receipt.objects.filter(shop=operation_type.shop, dttm__lt=dttm_for_delete)