import pandas

from src.db.models import PeriodDemand, Shop, CashboxType


def create_demand(path, shops, codes):
    cashbox_types = {}
    for it in range(len(shops)):
        cashbox_types[codes[it]] = CashboxType.objects.filter(shop_id=shops[it]).first()


    data = pandas.read_csv(path)
    data['datetime'] = pandas.to_datetime(data['datetime'])
    inst = []
    for i, row in data.iterrows():
        if row['Depart'] in cashbox_types.keys():
            inst.append(
                PeriodDemand(
                    dttm_forecast=row['datetime'],
                    type=PeriodDemand.Type.LONG_FORECAST.value,
                    cashbox_type=cashbox_types[row['Depart']],
                    clients=row['predict2'],
                    products=0,
                    queue_wait_time=0,
                    queue_wait_length=0,
                )
            )
            if len(inst) > 500:
                PeriodDemand.objects.bulk_create(inst)
                inst = []
    if len(inst):
        PeriodDemand.objects.bulk_create(inst)