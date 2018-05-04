import datetime
import os
import random

from src.db.models import Shop, PeriodDemand, CashboxType


class DataParseHelper(object):
    @classmethod
    def parse_datetime(cls, value):
        return datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S')

    @classmethod
    def parse_w_time(cls, value):
        return float(value)

    @classmethod
    def parse_length(cls, value):
        return float(value)


def load_csv(path, skip_rows=0):
    data = []
    with open(path) as f:
        counter = 0
        for line in f:
            counter += 1
            if counter <= skip_rows:
                continue

            arr = line.strip().split(',')
            if len(arr) != 3:
                print('skip line {} with data "{}"'.format(counter, line))
                continue

            data.append([
                DataParseHelper.parse_datetime(arr[0]),
                DataParseHelper.parse_length(arr[1]),
                DataParseHelper.parse_w_time(arr[2])
            ])

    return data


def run(path, super_shop):
    data = load_csv(os.path.join(path, 'demand_m05_line_q.csv'), skip_rows=1)
    shop = Shop.objects.get(super_shop=super_shop, hidden_title='common_magnit')
    cashbox_type = CashboxType.objects.get(shop=shop, name='Линия')
    counter = 0
    for x in data:
        counter += PeriodDemand.objects.filter(
            cashbox_type=cashbox_type,
            type=PeriodDemand.Type.LONG_FORECAST.value,
            dttm_forecast=x[0]  - datetime.timedelta(days=10),
        ).update(
            queue_wait_time=x[2] * 1.4 / (0.5 + random.random() / 2),
            queue_wait_length=x[1] * 1.4 / (0.5 + random.random() / 2),
        )

    print('demand_05_line_q updated {}'.format(counter))
    counter = 0

    data = load_csv(os.path.join(path, 'demand_m05_ret_q.csv'), skip_rows=1)
    cashbox_type = CashboxType.objects.get(shop=shop, name='Возврат')
    for x in data:
        counter += PeriodDemand.objects.filter(
            cashbox_type=cashbox_type,
            type=PeriodDemand.Type.LONG_FORECAST.value,
            dttm_forecast=x[0]  - datetime.timedelta(days=10),
        ).update(
            queue_wait_time=x[2] * 1.4 / (0.5 + random.random() / 2),
            queue_wait_length=x[1] * 1.4 / (0.5 + random.random() / 2),
        )

    print('demand_05_ret_q updated {}'.format(counter))
