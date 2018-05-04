import pandas

from src.db.models import PeriodDemand, Shop, CashboxType


def run(path):
    shop = Shop.objects.get(super_shop__code='004', title='Кассиры')
    print(shop.__dict__)
    # save_updating_demand(path, shop)
    create_demand(path, shop)


def safe_updating_demand(path, shop):
    cashbox_types = {
        'usual': CashboxType.objects.get(shop=shop, name='Линия'),
        'return': CashboxType.objects.get(shop=shop, name='Возврат'),
        'deli': CashboxType.objects.get(shop=shop, name='Доставка'),
        'info': CashboxType.objects.get(shop=shop, name='Информация')
    }

    data = pandas.read_csv(path)
    data['datetime'] = pandas.to_datetime(data['datetime'])
    for i, row in data.iterrows():
        print(i)
        if row['CashType'] in cashbox_types.keys():
            PeriodDemand.objects.update_or_create(
                dttm_forecast=row['datetime'],
                type=PeriodDemand.Type.LONG_FORECAST.value,
                cashbox_type=cashbox_types[row['CashType']],

                defaults={
                    'clients':row['predict2'],
                    'products': 0,
                    'queue_wait_time': 0,
                    'queue_wait_length':0,
                }
            )


def create_demand(path, shop):
    cashbox_types = {
        'usual': CashboxType.objects.get(shop=shop, name='Линия'),
        'return': CashboxType.objects.get(shop=shop, name='Возврат'),
        'deli': CashboxType.objects.get(shop=shop, name='Доставка'),
        'info': CashboxType.objects.get(shop=shop, name='Информация')
    }

    data = pandas.read_csv(path)
    data['datetime'] = pandas.to_datetime(data['datetime'])
    inst = []
    for i, row in data.iterrows():
        if row['CashType'] in cashbox_types.keys():
            inst.append(
                PeriodDemand(
                    dttm_forecast=row['datetime'],
                    type=PeriodDemand.Type.LONG_FORECAST.value,
                    cashbox_type=cashbox_types[row['CashType']],
                    clients=row['predict2'],
                    products=0,
                    queue_wait_time=0,
                    queue_wait_length=0,
                )
            )
            if len(inst) > 500:
                PeriodDemand.objects.bulk_create(inst)
                inst = []


