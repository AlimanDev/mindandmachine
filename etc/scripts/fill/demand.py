from datetime import time, datetime, timedelta, date

from dateutil.relativedelta import relativedelta
from django.db import transaction

from src.forecast.models import (
    OperationType,
    PeriodClients,
)


def fill_demand(shop_ids: list, dt_from=None, dt_to=None, value=1, delete_first=False):
    """
    Проставление нулевой нагрузки:
    from etc.scripts.fill.demand import fill_demand
    from datetime import date
    shop_ids = [171, 119]
    dt_from = date(2021, 5, 1)
    dt_to = date(2021, 5, 31)
    value = 0
    fill_demand(shop_ids=shop_ids, dt_from=dt_from, dt_to=dt_to, value=value, delete_first=True)
    """
    with transaction.atomic():
        dt_from = dt_from or date.today().replace(day=1)
        dt_to = dt_to or dt_from + relativedelta(months=2)
        dttms = [
            datetime.combine(dt_from + timedelta(i), time(j))
            for i in range((dt_to - dt_from).days)
            for j in range(24)
        ]
        if delete_first:
            PeriodClients.objects.filter(
                type=PeriodClients.LONG_FORECASE_TYPE,
                operation_type__shop_id__in=shop_ids,
                dttm_forecast__date__gte=dt_from,
                dttm_forecast__date__lte=dt_to,
            ).delete()
        period_clients = [
            PeriodClients(
                value=value,
                operation_type=o_type,
                type=PeriodClients.LONG_FORECASE_TYPE,
                dttm_forecast=dttm,
            )
            for o_type in OperationType.objects.filter(work_type__shop_id__in=shop_ids)
            for dttm in dttms
        ]
        PeriodClients.objects.bulk_create(period_clients)
