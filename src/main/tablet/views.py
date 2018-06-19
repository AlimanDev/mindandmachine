from datetime import datetime, timedelta, time

from src.db.models import Shop, CameraCashboxStat, CashboxType
from django.db.models import Avg

from src.util.collection import range_u
from src.util.models_converter import BaseConverter, PeriodDemandConverter, PeriodDemandChangeLogConverter
from src.util.utils import api_method, JsonResponse
from .forms import GetCashboxesInfo


@api_method('GET', GetCashboxesInfo)
def get_cashboxes_info(request, form):
    shop = Shop.objects.get(id=form['shop_id'])

    last_update_queue = CashboxType.objects.all().values('id')
    mean=0
    # for items in last_update_queue:
    mean_queue = CameraCashboxStat.objects.all().filter(
        camera_cashbox__cashbox__type__id=1,
    ).values('queue') \
        .aggregate(mean_queue=Avg('queue'))




    # for items in last_update_queue:
    #     mean_queue = CameraCashboxStat.objects.all().filter(
    #             camera_cashbox__cashbox__type__id=items['id']).order_by('dttm').values('queue').aggregate(mean_queue=Avg('queue'))
    #     mean = mean_queue
    # # print(mean_queue)
    if mean_queue['mean_queue']:
        return JsonResponse.success({
                'q' : mean_queue['mean_queue'],
            })
    else:
        return JsonResponse.success({
            'q': 0,
        })


def update_queue():
    last_update_queue = CashboxType.objects.all().filter(dttm_last_update_queue__isnull=False) \
        .values('id', 'dttm_last_update_queue')
    for items in last_update_queue:

        dif_time = (now() - items['dttm_last_update_queue'])
        while (dif_time.seconds > 1800) and dif_time.days >= 0:
            mean_queue = CameraCashboxStat.objects.all().filter(
                camera_cashbox__cashbox__type__id=items['id'],
                dttm__gte=items['dttm_last_update_queue'],
                dttm__lt=items['dttm_last_update_queue'] + timedelta(seconds=1800)
            ).values('queue') \
                .aggregate(mean_queue=Avg('queue'))

            period_demand = PeriodDemand.objects.all().filter(dttm_forecast=items['dttm_last_update_queue'],
                                                              cashbox_type_id=items['id'], type=3).values()
            if mean_queue['mean_queue']:
                if not period_demand:
                    PeriodDemand.objects.create(
                        dttm_forecast=items['dttm_last_update_queue'],
                        clients=0,
                        products=0,
                        type=3,
                        queue_wait_time=0,
                        queue_wait_length=mean_queue['mean_queue'],
                        cashbox_type_id=items['id']
                    )
                else:
                    PeriodDemand.objects.filter(dttm_forecast=items['dttm_last_update_queue'],
                                                cashbox_type_id=items['id']) \
                        .update(queue_wait_length=mean_queue['mean_queue'])
            CashboxType.objects.filter(id=items['id']) \
                .update(dttm_last_update_queue=items['dttm_last_update_queue'] + timedelta(seconds=1800))
            items['dttm_last_update_queue'] += timedelta(seconds=1800)
            dif_time -= timedelta(seconds=1800)
