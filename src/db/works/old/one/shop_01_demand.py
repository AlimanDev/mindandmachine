import datetime

from src.db.models import Shop, CashboxType, PeriodDemand


class DataParseHelper(object):
    @classmethod
    def parse_datetime(cls, value):
        return datetime.datetime.strptime(value, '%Y-%m-%d %H:%M:%S')

    @classmethod
    def parse_cashbox_type_name(cls, value):
        mapping = {
            'info': 'Информация',
            'return': 'Возврат',
            'usual': 'Линия',
            'fast': 'Быстрая',
            'deli': 'Доставка',
            'give': 'Выдача',
            'extra': 'Другое'
        }
        return mapping[value]

    @classmethod
    def parse_clients_count(cls, value):
        value = float(value)
        return max(value, 0)


def load_csv(path, skip_rows=0):
    data = []
    with open(path) as f:
        counter = 0
        for line in f:
            counter += 1
            if counter <= skip_rows:
                continue

            arr = line.strip().split(',')
            if len(arr) != 4:
                print('skip line {} with data "{}"'.format(counter, line))
                continue

            data.append([
                DataParseHelper.parse_datetime(arr[1]),
                DataParseHelper.parse_clients_count(arr[2]),
                DataParseHelper.parse_cashbox_type_name(arr[3])
            ])

    return data


def run():
    verbose = True

    def __print(*args, **kwargs):
        if verbose:
            print(*args, **kwargs)

    shop = Shop.objects.get(title='SHOP_ONE')
    cashboxes_types = {x.name: x for x in CashboxType.objects.filter(shop=shop)}

    path = 'src/db/works/parser/one/shop_01_demand.csv'
    data = load_csv(path, skip_rows=1)

    PeriodDemand.objects.all().delete()
    __print('PeriodDemand cleared')

    created_counter = {}
    non_created_counter = {}
    for row in data:
        cashbox_type = cashboxes_types.get(row[2])
        if cashbox_type is not None:
            pd = PeriodDemand.objects.create(
                dttm_forecast=row[0],
                clients=row[1],
                products=0,
                type=PeriodDemand.Type.LONG_FORECAST.value,
                cashbox_type=cashbox_type,
                queue_wait_time=0,
                queue_wait_length=0
            )

            if cashbox_type.name not in created_counter:
                created_counter[cashbox_type.name] = 0
            created_counter[cashbox_type.name] += 1
        else:
            name = row[2]
            if name not in non_created_counter:
                non_created_counter[name] = 0
            non_created_counter[name] += 1

    __print('PeriodDemand created count {}'.format(created_counter))
    __print('PeriodDemand NOT created count {}'.format(non_created_counter))
