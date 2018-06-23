from datetime import timedelta

from src.db.models import CameraCashboxStat, Cashbox, WorkerDayCashboxDetails, User
from django.db.models import Avg

from src.util.utils import api_method, JsonResponse
from .forms import GetCashboxesInfo, GetCashiersInfo
from django.utils.timezone import now


@api_method('GET', GetCashboxesInfo)
def get_cashboxes_info(request, form):
    response = {}
    dttm_now = now()
    shop_id = form['shop_id']

    list_of_cashbox = Cashbox.objects.qos_filter_active(
        dttm_now,
        dttm_now,
        type__shop__id=shop_id).order_by('number')

    for cashbox in list_of_cashbox:
        mean_queue = ''
        if cashbox.type.dttm_last_update_queue is None:
            with_queue = False

        else:
            with_queue = True
            mean_queue = CameraCashboxStat.objects.filter(
                camera_cashbox__cashbox__id=cashbox.id,
                dttm__gte=dttm_now - timedelta(seconds=60),
                dttm__lt=dttm_now).aggregate(mean_queue=Avg('queue'))
            if mean_queue:
                mean_queue = mean_queue['mean_queue']

        status = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
            on_cashbox__id=cashbox.id,
            tm_from__lt=dttm_now.time(),
            tm_to__gte=dttm_now.time(),
            on_cashbox=cashbox.id,
            cashbox_type__id=cashbox.type.id,
            worker_day__dt=dttm_now.date(),
            worker_day__worker_shop__id=shop_id
        )

        user_id = ''
        if not status:
            status = 'C'
        else:
            status = 'O'
            user_id = str(status[0].worker_day.worker_id)

        if cashbox.type.id not in response:
            response[cashbox.type.id] = \
                {
                    "name": cashbox.type.name,
                    "with_queue": with_queue,
                    "cashbox": []
                }

        response[cashbox.type.id]["cashbox"] += \
            {
                "number": cashbox.number,
                "status": status,
                "queue": mean_queue,
                "user_id": user_id,
            },

    return JsonResponse.success(response)


@api_method('GET', GetCashiersInfo)
def get_cashiers_info(request, form):
    shop_id = form['shop_id']
    dttm = form['dttm']

    response = {"Users": []}

    status = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
        worker_day__tm_work_start__lte=(dttm + timedelta(seconds=1800)).time(),
        worker_day__tm_work_end__gt=dttm.time(),
        worker_day__dt=dttm.date(),
        worker_day__worker_shop__id=shop_id
    ).order_by('tm_from')
    for item in status:
        if item.worker_day.tm_work_start > dttm.time():
            user_status = 'C'
        else:
            if item.is_break is True:
                user_status = 'B'
            elif item.on_education is True:
                user_status = 'S'
            else:
                user_status = 'W'

        tm_work_end = item.worker_day.tm_work_end
        tm_work_start = item.worker_day.tm_work_start

        duration_of_work = (tm_work_end.hour * 3600 + tm_work_end.minute * 60 + tm_work_end.second -
                            tm_work_start.hour * 3600 - tm_work_start.minute * 60 - tm_work_start.second) / 60

        import json
        break_triplets = item.cashbox_type.shop.break_triplets
        list_of_break_triplets = json.load(break_triplets)
        for item in break_triplets:
            # if duration_of_work> item[0] and duration_of_work < item[1]:
            #     list_of_break_triplets = item[3]
            response = {str(now()): str(json.dumps(list_of_break_triplets[0]))}

        #
        # response["Users"] += {
        #     "user_id": str(item.worker_day.worker.id),
        #     "status": user_status,
        #     "worker_day": str(item.worker_day.dt),
        #     "first_name": str(item.worker_day.worker.first_name),
        #     "last_name": str(item.worker_day.worker.last_name),
        #
        #     "tm_work_start": str(item.worker_day.tm_work_start),
        #     "tm_work_end": str(item.worker_day.tm_work_end),
        #     "cashbox": str(item.on_cashbox.id),
        #     "break_triplets": break_triplets,
        # },
    return JsonResponse.success(response)
