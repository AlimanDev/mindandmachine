from datetime import timedelta
import json

from src.db.models import CameraCashboxStat, Cashbox, WorkerDayCashboxDetails, User, PeriodDemand, WorkerDay
from django.db.models import Avg

from src.util.utils import api_method, JsonResponse
from .forms import GetCashboxesInfo, GetCashiersInfo, ChangeCashierStatus
from django.utils.timezone import now


@api_method('GET', GetCashboxesInfo)
def get_cashboxes_info(request, form):
    response = {}
    dttm_now = now()
    shop_id = form['shop_id']

    list_of_cashbox = Cashbox.objects.qos_filter_active(
        dttm_now,
        dttm_now,
        type__shop_id=shop_id).order_by('number')

    for cashbox in list_of_cashbox:
        mean_queue = None
        if cashbox.type.dttm_last_update_queue is None:
            with_queue = False

        else:
            with_queue = True
            mean_queue = CameraCashboxStat.objects.filter(
                camera_cashbox__cashbox_id=cashbox.id,
                dttm__gte=dttm_now - timedelta(seconds=60),
                dttm__lt=dttm_now).aggregate(mean_queue=Avg('queue'))
            if mean_queue:
                mean_queue = mean_queue['mean_queue']

        status = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
            on_cashbox=cashbox,
            tm_from__lt=dttm_now.time(),
            tm_to__gte=dttm_now.time(),
            cashbox_type_id=cashbox.type_id,
            worker_day__dt=dttm_now.date(),
            worker_day__worker_shop_id=shop_id
        )
        user_id = None
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
                "cashbox_id": cashbox.id,
                "status": status,
                "queue": mean_queue,
                "user_id": user_id,
            },

    return JsonResponse.success(response)


@api_method('GET', GetCashiersInfo)
def get_cashiers_info(request, form):
    shop_id = form['shop_id']
    dttm = form['dttm']
    response = {}

    status = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
        worker_day__tm_work_start__lte=(dttm + timedelta(seconds=1800)).time(),
        worker_day__tm_work_end__gt=dttm.time(),
        worker_day__dt=dttm.date(),
        worker_day__worker_shop__id=shop_id,
    ).order_by('tm_from')

    for item in status:
        triplets = []
        user_status = None
        real_break_time = None

        tm_work_end = item.worker_day.tm_work_end
        tm_work_start = item.worker_day.tm_work_start

        duration_of_work = float(
            tm_work_end.hour * 3600 + tm_work_end.minute * 60 + tm_work_end.second -
            tm_work_start.hour * 3600 - tm_work_start.minute * 60 - tm_work_start.second) / 60
        break_triplets = item.cashbox_type.shop.break_triplets
        list_of_break_triplets = json.loads(break_triplets)

        for triplet in list_of_break_triplets:
            if float(triplet[0]) < duration_of_work <= float(triplet[1]):
                for time_triplet in triplet[2]:
                    triplets.append([time_triplet, 0])

        if item.worker_day.tm_work_start > dttm.time():
            user_status = 'C'
        else:
            if item.is_tablet is True:
                if item.is_break is True:
                    user_status = 'B'
                    if item.tm_to:
                        real_break_time = float(item.tm_to.hour * 3600 + item.tm_to.minute * 60 + item.tm_to.second -
                                                item.tm_from.hour * 3600 - item.tm_from.minute * 60 -
                                                item.tm_from.second) / 60

                        for triplet in list_of_break_triplets:

                            if float(triplet[0]) < duration_of_work <= float(triplet[1]):
                                if response.get(item.worker_day.worker_id):
                                    triplets = response[item.worker_day.worker_id][0]['break_triplets']
                                    for it in triplets:
                                        if it[1] == 0:
                                            if real_break_time:
                                                it[0] = real_break_time
                                            it[1] = 1
                                            break
                                    else:
                                        triplets.append([real_break_time, 1])
                                break
                elif item.on_education is True:
                    user_status = 'S'
                elif (item.is_break is False) and item.tm_to:
                    user_status = 'H'
                elif item.worker_day.type == WorkerDay.Type.TYPE_ABSENSE.value:
                    user_status = 'A'
                else:
                    user_status = 'W'
        cashbox_dttm_added = None
        cashbox_dttm_deleted = None
        cashbox_type = None
        cashbox_number = None
        if item.on_cashbox_id:
            cashbox_dttm_added = str(item.on_cashbox.dttm_added)
            cashbox_dttm_deleted = str(item.on_cashbox.dttm_deleted)
            cashbox_type = item.on_cashbox.type_id
            cashbox_number = item.on_cashbox.number

        if item.worker_day.worker_id not in response.keys():
            response[item.worker_day.worker_id] = {
                                                      "worker_id": item.worker_day.worker_id,
                                                      "status": user_status,
                                                      "worker_day_id": item.worker_day_id,
                                                      "tm_work_start": str(item.worker_day.tm_work_start),
                                                      "tm_work_end": str(item.worker_day.tm_work_end),
                                                      "break_triplets": triplets,
                                                      "cashbox_id": item.on_cashbox_id,
                                                      "cashbox_dttm_added": cashbox_dttm_added,
                                                      "cashbox_dttm_deleted": cashbox_dttm_deleted,
                                                      "cashbox_type": cashbox_type,
                                                      "cashbox_number": cashbox_number,
                                                  },

        else:
            response[item.worker_day.worker_id][0]["status"] = user_status

    return JsonResponse.success(response)


@api_method('POST', ChangeCashierStatus)
def change_cashier_status(request, form):
    worker_id = form['worker_id']
    new_user_status = form['status']
    cashbox_id = form['cashbox_id']

    response = {}
    dttm_now = now()

    def change_status(item, is_break=False, is_on_education=False, is_tablet=True):
        if is_tablet is True:
            item.tm_to = dttm_now.time()
            item.save()
            pd = item
            pd.pk = None
            pd.tm_from = dttm_now.time()
            pd.tm_to = None
            pd.on_education = is_on_education
            pd.is_break = is_break
            pd.save()
        else:
            item.tm_from = dttm_now.time()
            item.is_tablet = True
            item.tm_to = None
            item.on_education = is_on_education
            item.is_break = is_break
            item.save()

    status = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
        worker_day__dt=dttm_now.date(),
        worker_day__worker_id=worker_id
    ).order_by('tm_from')
    user_status = None

    if status:

        for item in status:
            if (item.is_tablet is True) and not item.tm_to:
                if new_user_status == 'W':
                    user_status = new_user_status
                    if cashbox_id:
                        item.on_cashbox_id = cashbox_id
                        item.save()
                    if item.is_break is True or item.on_education is True:
                        change_status(item)
                    break

                elif new_user_status == 'B':
                    user_status = new_user_status
                    if item.is_break is False:
                        change_status(item, is_break=True)
                    break

                elif new_user_status == 'A':
                    return JsonResponse.value_error(
                        'can not change the status to {}'.format(new_user_status))

                elif new_user_status == 'S':
                    user_status = new_user_status

                    if item.on_education is False:
                        change_status(item, is_on_education=True)
                    break

                elif new_user_status == 'H':

                    if (item.worker_day.type != WorkerDay.Type.TYPE_ABSENSE.value) and (user_status != 'C'):

                        item.tm_to = dttm_now.time()
                        item.on_education = False
                        item.is_break = False
                        item.save()
                        break

                    else:
                        return JsonResponse.value_error(
                            'can not change the status to {}'.format(new_user_status))
                else:
                    return JsonResponse.value_error(
                        'Invalid status {}'.format(new_user_status))

            elif (item.is_tablet is False) and item.tm_to:
                if new_user_status == 'W':
                    user_status = 'W'
                    if cashbox_id:
                        item.on_cashbox_id = cashbox_id
                        item.save()
                    if item.worker_day.type == WorkerDay.Type.TYPE_ABSENSE.value:
                        # A если был не выходной....
                        item.worker_day.type = WorkerDay.Type.TYPE_WORKDAY.value
                        item.worker_day.save()
                    change_status(item, is_tablet=False)
                    break

                elif new_user_status == 'B':
                    user_status = 'B'
                    if item.worker_day.type == WorkerDay.Type.TYPE_ABSENSE.value:
                        # A если был не выходной....
                        item.worker_day.type = WorkerDay.Type.TYPE_WORKDAY.value
                        item.worker_day.save()
                    change_status(item, is_break=True, is_tablet=False)
                    break

                elif new_user_status == 'A':
                    user_status = 'A'
                    item.worker_day.type = WorkerDay.Type.TYPE_ABSENSE.value
                    item.worker_day.save()
                    break

                elif new_user_status == 'S':
                    user_status = 'S'
                    if item.worker_day.type == WorkerDay.Type.TYPE_ABSENSE.value:
                        # A если был не выходной....
                        item.worker_day.type = WorkerDay.Type.TYPE_WORKDAY.value
                        item.worker_day.save()
                    change_status(item, is_on_education=True, is_tablet=False)
                    break

                elif new_user_status == 'H':
                    return JsonResponse.value_error(
                        'can not change the status to {}'.format(new_user_status))
                else:
                    return JsonResponse.value_error(
                        'Invalid status {}'.format(new_user_status))

        else:
            user_status = 'H'

        response[item.worker_day.worker_id] = {
                                                  "worker_id": item.worker_day.worker_id,
                                                  "status": user_status,
                                                  "cashbox_id": item.on_cashbox_id,
                                              },

    return JsonResponse.success(response)
