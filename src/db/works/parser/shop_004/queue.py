import random
from datetime import datetime, timedelta

from src.db.models import Shop, CashboxType, WaitTimeInfo, PeriodDemand
from src.util.collection import range_u


def run():
    dttm_from = datetime.now() - timedelta(days=30)
    dttm_to = datetime.now()
    dttm_step = timedelta(days=1)

    shop = Shop.objects.get(title='Алтуфьево')
    cashboxes_types = CashboxType.objects.filter(shop=shop)

    for dttm in range_u(dttm_from, dttm_to, dttm_step):
        for ct in cashboxes_types:
            for forecast_type in PeriodDemand.Type.values():
                wt = random.randint(1, 9)
                WaitTimeInfo.objects.create(
                    dt=dttm.date(),
                    cashbox_type=ct,
                    wait_time=wt,
                    proportion=min(1 - wt / 10, 0.95),
                    type=forecast_type
                )
