from src.db.models import PeriodDemand, CashboxType, CameraCashboxStat

from datetime import timedelta
from django.db.models import Avg

from django.utils.timezone import now


def update_queue():
    cashbox_types = CashboxType.objects.filter(
        dttm_last_update_queue__isnull=False)
    for items in cashbox_types:
        dif_time = (now() - items.dttm_last_update_queue).total_seconds()
        while dif_time > 1800:

            mean_queue = CameraCashboxStat.objects.filter(
                camera_cashbox__cashbox__type__id=items.id,
                dttm__gte=items.dttm_last_update_queue,
                dttm__lt=items.dttm_last_update_queue + timedelta(seconds=1800)
            ).aggregate(mean_queue=Avg('queue'))

            period_demand = PeriodDemand.objects.filter(
                dttm_forecast=items.dttm_last_update_queue,
                cashbox_type_id=items.id,
                type=PeriodDemand.Type.FACT.value
            )

            if mean_queue['mean_queue']:
                if not period_demand:
                    PeriodDemand.objects.create(
                        dttm_forecast=items.dttm_last_update_queue,
                        clients=0,
                        products=0,
                        type=PeriodDemand.Type.FACT.value,
                        queue_wait_time=0,
                        queue_wait_length=mean_queue['mean_queue'],
                        cashbox_type_id=items.id
                    )
                else:
                    pd = period_demand[0]
                    pd.queue_wait_length = mean_queue['mean_queue']
                    pd.save()

            items.dttm_last_update_queue += timedelta(seconds=1800)
            dif_time -= 1800

        pd = items
        pd.dttm_last_update_queue = items.dttm_last_update_queue + timedelta(seconds=1800)
        pd.save()
