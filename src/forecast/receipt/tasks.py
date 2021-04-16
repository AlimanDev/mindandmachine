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
                'timeserie_action': ['count', 'sum'],
                'timeserie_value': какое значение для агрегации использовать,
                'timeserie_filters': словарь, например: {"ВидОперации": "Продажа"}
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
                for aggregate in timeserie['aggregate']:
                    aggr_filters = aggregate.get('timeserie_filters')
                    timeserie_action = aggregate.get('timeserie_action', 'sum')
                    dttm_for_update = (datetime.now() - timedelta(days=update_gap)).replace(hour=0, minute=0, second=0)

                    # check all needed
                    if not (aggregate.get('timeserie_code') and aggregate.get('timeserie_value')):
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
                        items_list = []
                        items = Receipt.objects.filter(shop=operation_type.shop, dttm__gte=dttm_for_update)
                        for item in items:
                            item.info = json.loads(item.info)

                            # Пропускаем записи, которые не удовл. значениям в фильтре
                            if aggr_filters and not all(item.info.get(k) == v for k, v in aggr_filters.items()):
                                continue
                            items_list.append({
                                'dttm': item.dttm,
                                'value': float(item.info.get(aggregate['timeserie_value'], 0))  # fixme: то ли ошибку лучше кидать, то ли пропускать (0 ставить)
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
                        Receipt.objects.filter(shop=operation_type.shop, dttm__lt=dttm_for_delete).delete()
