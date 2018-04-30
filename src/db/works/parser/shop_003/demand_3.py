import datetime
import os

from src.db.models import Shop, PeriodDemand, CashboxType


class DataParseHelper(object):
    @classmethod
    def parse_datetime(cls, value):
        return datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S')

    @classmethod
    def parse_clients(cls, value):
        return max(float(value), 0)

    @classmethod
    def parse_depart(cls, value):
        return int(value)


def load_csv(path, skip_rows=0):
    data = []
    with open(path) as f:
        counter = 0
        for line in f:
            counter += 1
            if counter <= skip_rows:
                continue

            arr = line.strip().split(',')
            if len(arr) != 5:
                print('skip line {} with data "{}"'.format(counter, line))
                continue

            data.append([
                DataParseHelper.parse_datetime(arr[1]),
                DataParseHelper.parse_clients(arr[2]),
                DataParseHelper.parse_depart(arr[3])
            ])

    return data


def run(path, super_shop):
    print('demand3_started')

    data = load_csv(os.path.join(path, 'demand_depart_m0506.csv'), skip_rows=1)
    shops = {
        3: Shop.objects.get(super_shop=super_shop, hidden_title='electro'),
        7: Shop.objects.get(super_shop=super_shop, hidden_title='santeh'),
        12: Shop.objects.get(super_shop=super_shop, hidden_title='dekor')
    }

    def __get_safe(__v):
        __data = CashboxType.objects.filter(shop=__v)
        return __data[0] if len(__data) > 0 else None

    cashboxes_types = {k: __get_safe(v) for k, v in shops.items()}
    counter = 0
    for x in data:
        dttm = x[0]
        clients = x[1]
        depart = x[2]
        if cashboxes_types.get(depart) is not None:
            PeriodDemand.objects.create(
                cashbox_type=cashboxes_types[depart],
                type=PeriodDemand.Type.LONG_FORECAST.value,
                dttm_forecast=dttm,
                clients=clients,
                products=0,
                queue_wait_time=0,
                queue_wait_length=0
            )
            counter += 1

    print('demand_depart updated {}'.format(counter))
