import pickle

from src.db.models import Shop, User, CashboxType, WorkerCashboxInfo


class DataParseHelper(object):
    @classmethod
    def parse_fio(cls, value):
        value = {i: v for i, v in enumerate(value.strip().split())}
        last_name = value.get(0, 'DEFAULT')
        first_name = value.get(1, 'DEFAULT')
        middle_name = value.get(2, 'DEFAULT')
        return first_name, middle_name, last_name

    @classmethod
    def parse_cashbox_type_name(cls, value):
        mapping = {
            'info': 'Информация',
            'return': 'Возврат',
            'usual': 'Линия',
            'fast': 'Быстрая',
            'deli': 'Доставка'
        }
        return mapping.get(value)


def run():
    verbose = True

    def __print(*args, **kwargs):
        if verbose:
            print(*args, **kwargs)

    shop = Shop.objects.get(title='SHOP_ONE')
    cashboxes_types = {x.name: x for x in CashboxType.objects.filter(shop=shop)}

    path = 'src/db/works/parser/one/shop_01_speed.pickle'
    with open(path, 'rb') as f:
        data = pickle.load(f)

    updated_rows_count = 0

    for row in data.values:
        first_name, middle_name, last_name = DataParseHelper.parse_fio(row[0])

        user = User.objects.get(shop=shop, first_name=first_name, middle_name=middle_name, last_name=last_name)
        for k, v in row[6].items():
            cashbox_type_name = DataParseHelper.parse_cashbox_type_name(k)
            cashbox_type = cashboxes_types.get(cashbox_type_name)

            if cashbox_type is not None:
                count = WorkerCashboxInfo.objects.filter(worker=user, cashbox_type=cashbox_type).update(mean_speed=v)
                updated_rows_count += count

    __print('updated rows {}'.format(updated_rows_count))
