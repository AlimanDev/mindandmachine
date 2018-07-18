import datetime as dt
from datetime import timedelta, datetime
import json

from src.db.models import CameraCashboxStat, Cashbox, WorkerDayCashboxDetails, User, PeriodDemand, WorkerDay, \
    CashboxType
from django.db.models import Avg
from src.conf.djconfig import QOS_DATETIME_FORMAT

from src.util.utils import api_method, JsonResponse
from .utils import time_diff, is_midnight_period
from .forms import GetCashboxesInfo, GetCashiersInfo, ChangeCashierStatus
from django.utils.timezone import now


@api_method('GET', GetCashboxesInfo)
def get_cashboxes_info(request, form):
    response = {}
    dttm_now = now() + timedelta(hours=3)

    shop_id = form['shop_id']

    list_of_cashbox = Cashbox.objects.qos_filter_active(
        dttm_now,
        dttm_now,
        type__shop_id=shop_id).order_by('type__priority').order_by('number').select_related('type')

    for cashbox in list_of_cashbox:
        mean_queue = None
        if cashbox.type.dttm_last_update_queue is None:
            with_queue = False

        else:
            with_queue = True
            # супер костыль в dttm__gte, так как время с камер пишется в UTC+6
            mean_queue = CameraCashboxStat.objects.filter(
                camera_cashbox__cashbox_id=cashbox.id,
                dttm__gte=dttm_now - timedelta(seconds=60) + timedelta(seconds=1080),
                dttm__lt=dttm_now + timedelta(seconds=1080)).aggregate(mean_queue=Avg('queue'))
            if mean_queue:
                mean_queue = mean_queue['mean_queue']

        status = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
            on_cashbox=cashbox,
            tm_to__isnull=True,
            worker_day__dt=(dttm_now-timedelta(hours=2)).date(),
            worker_day__worker_shop=shop_id,
        )

        user_id = None
        if not status:
            status = 'C'
        else:
            user_id = str(status[0].worker_day.worker_id)
            status = 'O'

        if cashbox.type.id not in response:
            response[cashbox.type.id] = \
                {
                    "name": cashbox.type.name,
                    "priority": cashbox.type.priority,
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

    tm_to_show_all_workers = dt.time(23, 59)  # в 23:59 уже можно показывать всех сотрудников
    # todo: сделать без привязки к времени

    status = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
        worker_day__tm_work_start__lte=(dttm + timedelta(minutes=30)).time() if not is_midnight_period(dttm)
                                        else tm_to_show_all_workers,
        worker_day__dt=(dttm - timedelta(hours=2)).date(),
        worker_day__worker_shop__id=shop_id,
    ).order_by('id')

    for item in status:
        triplets = []
        default_break_triplets = []

        user_status = None
        real_break_time = None
        time_without_rest = None

        tm_work_end = item.worker_day.tm_work_end
        tm_work_start = item.worker_day.tm_work_start

        duration_of_work = round(time_diff(tm_work_start, tm_work_end) / 60)

        break_triplets = item.cashbox_type.shop.break_triplets
        list_of_break_triplets = json.loads(break_triplets)
        for triplet in list_of_break_triplets:
            if float(triplet[0]) < duration_of_work <= float(triplet[1]):
                for time_triplet in triplet[2]:
                    triplets.append([time_triplet, 0])
                    default_break_triplets.append(time_triplet)

        if item.worker_day.tm_work_start > dttm.time() and item.worker_day.dt == dttm.date():
            user_status = 'C'
        else:
            if item.is_tablet is True:
                if item.is_break is True:
                    user_status = 'B'

                    break_end = item.tm_to

                    if item.tm_to is None:
                        break_end = dttm.time()
                    if item.tm_from is None:
                        item.tm_from = dttm.time()
                    real_break_time = time_diff(item.tm_from, break_end)

                    for triplet in list_of_break_triplets:
                        if int(triplet[0]) < duration_of_work <= int(triplet[1]):
                            if response.get(item.worker_day.worker_id):
                                triplets = response[item.worker_day.worker_id][0]['break_triplets']
                                for it in triplets:
                                    if it[1] == 0:
                                        if real_break_time >= 0:
                                            it[1] = round(float(real_break_time) / 60)
                                        it[0] = 1
                                        break
                                else:
                                    triplets.append([1, round(float(real_break_time)/60)])
                            break
                elif item.on_education is True:
                    user_status = 'S'
                elif (item.is_break is False) and item.tm_to:
                    user_status = 'H'
                elif item.worker_day.type == WorkerDay.Type.TYPE_ABSENSE.value:
                    user_status = 'A'
                else:
                    user_status = 'W'
                if not item.tm_to and item.on_cashbox:
                    time_without_rest = round(time_diff(item.tm_from, dttm.time()) / 60)
            else:
                user_status = 'T'

        cashbox_dttm_added = None
        cashbox_dttm_deleted = None
        cashbox_number = None
        cashbox_type = item.cashbox_type_id

        if item.on_cashbox_id:
            cashbox_dttm_added = str(item.on_cashbox.dttm_added)
            cashbox_dttm_deleted = str(item.on_cashbox.dttm_deleted)
            cashbox_number = item.on_cashbox.number

        if item.worker_day.worker_id not in response.keys():
            response[item.worker_day.worker_id] = {
                                                      "worker_id": item.worker_day.worker_id,
                                                      "status": user_status,
                                                      "worker_day_id": item.worker_day_id,
                                                      "tm_work_start": str(item.tm_from),
                                                      "tm_work_end": str(item.worker_day.tm_work_end),
                                                      "default_break_triplets": str(default_break_triplets),
                                                      "break_triplets": triplets,
                                                      "cashbox_id": item.on_cashbox_id,
                                                      "cashbox_dttm_added": cashbox_dttm_added,
                                                      "cashbox_dttm_deleted": cashbox_dttm_deleted,
                                                      "cashbox_type": cashbox_type,
                                                      "cashbox_number": cashbox_number,
                                                      "time_without_rest": time_without_rest,
                                                  },

        else:
            response[item.worker_day.worker_id][0]["status"] = user_status
            response[item.worker_day.worker_id][0]["cashbox_id"] = item.on_cashbox_id
            response[item.worker_day.worker_id][0]["cashbox_dttm_added"] = cashbox_dttm_added
            response[item.worker_day.worker_id][0]["cashbox_dttm_deleted"] = cashbox_dttm_deleted
            response[item.worker_day.worker_id][0]["cashbox_number"] = cashbox_number
            response[item.worker_day.worker_id][0]["time_without_rest"] = time_without_rest
            response[item.worker_day.worker_id][0]["tm_work_end"] = str(item.tm_to if user_status is 'H' else item.worker_day.tm_work_end)
    return JsonResponse.success(response)


@api_method('POST', ChangeCashierStatus)
def change_cashier_status(request, form):
    worker_id = form['worker_id']
    new_user_status = form['status']
    cashbox_id = form['cashbox_id']
    is_current_time = form['is_current_time']

    response = {}
    dttm_now = datetime.strptime(datetime.strftime(now() + timedelta(hours=3), QOS_DATETIME_FORMAT),
                                 QOS_DATETIME_FORMAT)

    # для тестирования. потом вообще надо будет убрать
    regular_day = dttm_now + timedelta(hours=9)
    dttm_shop_closes = dt.datetime(dttm_now.year, dttm_now.month, dttm_now.day + 1, 1, 0, 0)\
        if dttm_now.time().hour > 2 else dt.datetime(dttm_now.year, dttm_now.month, dttm_now.day, 1, 0, 0)
    tm_work_end = form['tm_work_end'] if form['tm_work_end'] else \
        regular_day.time() if regular_day < dttm_shop_closes \
            else dttm_shop_closes.time()
    # todo: upd: вообще убрать потом когда tm_work_end будет реализовано на фронте

    def change_status(item, is_break=False, is_on_education=False, is_tablet=True, new_cashbox_id=False):
        if is_tablet is True:
            item.tm_to = dttm_now.time()
            item.save()
            pd = item
            pd.pk = None
            pd.tm_from = dttm_now.time()
            pd.tm_to = None
            if new_user_status is not False:
                pd.on_cashbox_id = new_cashbox_id
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
        worker_day__dt=(dttm_now-timedelta(hours=2)).date(),
        worker_day__worker_id=worker_id
    ).order_by('id')
    user_status = None

    if not status:
        WorkerDay.objects.filter(worker_id=worker_id, dt=dttm_now.date()). \
            update(type=WorkerDay.Type.TYPE_WORKDAY.value, tm_work_start=dttm_now.time(), tm_work_end=tm_work_end)

        status = WorkerDayCashboxDetails.objects.create(
            worker_day=WorkerDay.objects.get(worker_id=worker_id, dt=dttm_now.date()),
            is_tablet=False,
            tm_from=dttm_now.time(),
            tm_to=tm_work_end,
            cashbox_type=CashboxType.objects.get(cashbox__id=cashbox_id)
        )
        status = [status]

    if status:
        for item in status:
            if (item.is_tablet is True) and not item.tm_to:
                if new_user_status == 'W':
                    user_status = new_user_status
                    if item.is_break is True or item.on_education is True:
                        change_status(item, new_cashbox_id=cashbox_id)
                        prev_item = item.__class__.objects.filter(worker_day=item.worker_day).order_by('-id')[1]
                        prev_item.tm_to = dttm_now.time()
                        prev_item.save()
                    else:
                        if cashbox_id and (cashbox_id != item.on_cashbox_id):
                            change_status(item, new_cashbox_id=cashbox_id)
                    break

                elif new_user_status == 'B':
                    user_status = new_user_status
                    if item.is_break is False:
                        change_status(item, is_break=True, new_cashbox_id=None)
                    break

                elif new_user_status == 'A':
                    return JsonResponse.value_error(
                        'can not change the status to {}'.format(new_user_status))

                elif new_user_status == 'S':
                    user_status = new_user_status
                    if item.on_education is False:
                        change_status(item, is_on_education=True, new_cashbox_id=None)
                    break

                elif new_user_status == 'H':
                    if (item.worker_day.type != WorkerDay.Type.TYPE_ABSENSE.value) and (user_status != 'C'):
                        user_status = 'H'
                        item.save()
                        item.tm_to = item.worker_day.tm_work_end if not is_current_time else dttm_now.time()
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
                    user_status = new_user_status
                    if cashbox_id:
                        item.on_cashbox_id = cashbox_id
                        item.save()
                    if item.worker_day.type == WorkerDay.Type.TYPE_ABSENSE.value:
                        # A если был не выходной....
                        item.worker_day.type = WorkerDay.Type.TYPE_WORKDAY.value
                        item.worker_day.save()
                    change_status(item, is_tablet=False)
                    if not is_current_time:
                        item.tm_from = item.worker_day.tm_work_start
                        item.save()
                    break

                elif new_user_status == 'B':
                    user_status = new_user_status
                    item.on_cashbox_id = None
                    item.save()
                    if item.worker_day.type == WorkerDay.Type.TYPE_ABSENSE.value:
                        # A если был не выходной....
                        item.worker_day.type = WorkerDay.Type.TYPE_WORKDAY.value
                        item.worker_day.save()
                    change_status(item, is_break=True, is_tablet=False)
                    break

                elif new_user_status == 'A':
                    user_status = new_user_status
                    item.worker_day.type = WorkerDay.Type.TYPE_ABSENSE.value
                    item.worker_day.save()
                    break

                elif new_user_status == 'S':
                    user_status = new_user_status
                    item.on_cashbox_id = None
                    item.save()
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
                                                  "cashbox_id": item.on_cashbox_id
                                              },

    return JsonResponse.success(response)
