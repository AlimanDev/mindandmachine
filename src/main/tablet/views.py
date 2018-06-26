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
            on_cashbox_id=cashbox.id,
            tm_from__lt=dttm_now.time(),
            tm_to__gte=dttm_now.time(),
            on_cashbox=cashbox.id,
            cashbox_type_id=cashbox.type.id,
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
        worker_day__worker_shop__id=shop_id
    ).order_by('tm_from')

    for item in status:
        user_status = None
        real_break_time = None

        if item.worker_day.tm_work_start > dttm.time():
            user_status = 'C'
        else:
            if item.is_tablet is True:
                if item.is_break is True:
                    user_status = 'B'
                    # if item.tm_to:
                    real_break_time = float(item.tm_to.hour * 3600 + item.tm_to.minute * 60 + item.tm_to.second -
                                            item.tm_from.hour * 3600 - item.tm_from.minute * 60 -
                                            item.tm_from.second) / 60
                elif item.on_education is True:
                    user_status = 'S'
                elif (item.is_break is False) and item.tm_to:
                    user_status = 'H'
                elif item.worker_day.type == WorkerDay.Type.TYPE_ABSENSE.value:
                    user_status = 'A'
                else:
                    user_status = 'W'

        tm_work_end = item.worker_day.tm_work_end
        tm_work_start = item.worker_day.tm_work_start

        duration_of_work = float(tm_work_end.hour * 3600 + tm_work_end.minute * 60 + tm_work_end.second -
                                 tm_work_start.hour * 3600 - tm_work_start.minute * 60 - tm_work_start.second) / 60

        break_triplets = item.cashbox_type.shop.break_triplets
        list_of_break_triplets = json.loads(break_triplets)
        triplets = []

        for triplet in list_of_break_triplets:

            if float(triplet[0]) < duration_of_work <= float(triplet[1]):
                if not response.get(item.worker_day.worker_id):
                    for time_triplet in triplet[2]:
                        triplets.append([time_triplet, 0])
                else:
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

        if item.worker_day.worker_id not in response.keys():
            response[item.worker_day.worker_id] = {
                                                      "status": user_status,
                                                      "worker_day": str(item.worker_day.dt),
                                                      "first_name": str(item.worker_day.worker.first_name),
                                                      "last_name": str(item.worker_day.worker.last_name),

                                                      "tm_work_start": str(item.worker_day.tm_work_start),
                                                      "tm_work_end": str(item.worker_day.tm_work_end),
                                                      "break_triplets": triplets,
                                                      "worker_day_id": str(item.worker_day_id),

                                                  },

    return JsonResponse.success(response)


@api_method('GET', ChangeCashierStatus)
def change_cashier_status(request, form):
    worker_id = form['worker_id']
    new_user_status = form['status']
    response = {}
    dttm_now = now()

    def change_status(item, is_break=False, is_on_education=False, is_tablet=True):
        if is_tablet is True:
            item.tm_to = dttm_now.time()
            item.save()
            pd = item
            # pd.id = None
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
        # worker_day__tm_work_start__lte=(dttm_now + timedelta(seconds=1800)).time(),
        # worker_day__tm_work_end__gt=dttm_now.time(),
        worker_day__dt=dttm_now.date(),
        worker_day__worker_id=worker_id
    ).order_by('tm_from')
    user_status = None

    if status:

        for item in status:
            real_break_time = None

            # if item.worker_day.tm_work_start > dttm_now.time():
            #     user_status = 'C'

            if item.is_tablet is True and not item.tm_to:
                # return JsonResponse.success({'Failed3': item.is_break})

                if new_user_status == 1:
                    user_status = 'W'

                    if item.is_break is True or item.on_education is True:
                        return JsonResponse.success({'Failed3': item.is_break})
                        # change_status(item)
                    break

                elif new_user_status == 2:
                    user_status = 'B'
                    # return JsonResponse.success({'Failed1': item.is_break})

                    if item.is_break is False:
                        # return JsonResponse.success({'Failed1': item.is_break})

                        change_status(item, is_break=True)
                    break

                elif new_user_status == 3:
                    # Exception
                    pass

                elif new_user_status == 4:
                    # Exception
                    pass

                elif new_user_status == 5:
                    user_status = 'S'

                    if item.on_education is False:

                        change_status(item, is_on_education=True)
                    break

                elif new_user_status == 6:

                    if (item.worker_day.type != WorkerDay.Type.TYPE_ABSENSE.value) and (user_status != 'C'):

                        item.tm_to = dttm_now.time()
                        item.save()
                        break

                    else:
                        return JsonResponse.success({'Failed': item.is_break})

                        # Exception
                        # pass



            elif item.is_tablet is False and item.tm_to:
                # return JsonResponse.success({item.is_tablet: item.id})

                # return JsonResponse.success()

                if new_user_status == 1:
                    user_status = 'W'

                    change_status(item, is_tablet=False)
                    break

                #     точно ли можно сразу в перерыв?
                elif new_user_status == 2:
                    user_status = 'W'

                    change_status(item, is_break=True, is_tablet=False)
                    break

                elif new_user_status == 3:
                    user_status = 'C'
                    item.tm_from = (dttm_now + timedelta(seconds=1800)).time()
                    # добавить, чтобы время tm_to было точное
                    item.save()
                    break

                elif new_user_status == 4:
                    item.worker_day.type = WorkerDay.Type.TYPE_ABSENSE.value
                    # Exception
                    pass

                elif new_user_status == 5:
                    user_status = 'S'
                    change_status(item, is_on_education=True, is_tablet=False)
                    break



        else:
            return JsonResponse.success({'Failed': item.id})

            # Exception
            pass
        response[item.worker_day.worker_id] = {
                                                  "status": user_status,
                                                  "worker_day": str(item.worker_day.dt),
                                                  "first_name": str(item.worker_day.worker.first_name),
                                                  "last_name": str(item.worker_day.worker.last_name),

                                                  "tm_work_start": str(item.tm_from),
                                                  "tm_work_end": str(item.tm_to),
                                                  "cashbox_id": item.on_cashbox_id,
                                                  "worker_day_id": str(item.worker_day_id),

                                                  "break": str(item.is_break),
                                                  "in_educ": item.on_education,

                                              },

    # else:
    #     x = WorkerDayCashboxDetails(
    #         worker_day=dttm_now.date(),
    #         on_cashbox=None
    #     )

    return JsonResponse.success(response)
