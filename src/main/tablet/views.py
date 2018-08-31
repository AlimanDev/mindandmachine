import datetime as datetime_module
from datetime import timedelta, datetime
from django.db.models import Q
import json

from src.db.models import (
    CameraCashboxStat,
    Cashbox,
    WorkerDayCashboxDetails,
    WorkerCashboxInfo,
    WorkerDay,
    CashboxType,
    Shop,
    User
)
from django.db.models import Avg

from src.util.utils import api_method, JsonResponse
from src.util.forms import FormUtil
from .utils import time_diff, is_midnight_period
from .forms import GetCashboxesInfo, GetCashiersInfo, ChangeCashierStatus
from django.utils.timezone import now
from src.util.models_converter import WorkerCashboxInfoConverter
from src.util.collection import group_by


@api_method('GET', GetCashboxesInfo)
def get_cashboxes_info(request, form):
    """
    Возвращает состояние каждой кассы в магазине

    Args:
        method: GET
        url: /api/tablet/get_cashboxes_info
        shop_id (int): required = False
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)

    Returns:
        {
            cashbox_type_id (int) :{
                'cashbox' : {
                    [
                        {
                            | 'number': номер кассы,
                            | 'cashbox_id': id кассы,
                            | 'user_id': id пользователя, который за ней сидит (либо null если касса пустая),
                            | 'queue': число человек в очереди, либо null,
                            | 'status': 'O' или 'C' -- открыта касса или закрыта
                        }
                    ], ...
                },

                'priority':
                    | для линии -- 1,
                    | для главной кассы -- 2,
                    | для экспресс касс -- 3,
                    | для остальных -- 100 (по дефолту)
                | 'with_queue': True/False,
                | 'name': имя cashbox_type_id
            }
        }
    """
    response = {}
    dttm_now = now() + timedelta(hours=3)

    shop_id = FormUtil.get_shop_id(request, form)
    checkpoint = FormUtil.get_checkpoint(form)

    list_of_cashbox = Cashbox.objects.qos_filter_active(
        dttm_now,
        dttm_now,
        type__shop_id=shop_id
    ).order_by('type__priority', 'number').select_related('type')

    for cashbox in list_of_cashbox:
        mean_queue = None
        if cashbox.type.dttm_last_update_queue is None:
            with_queue = False

        else:
            with_queue = True
            # супер костыль в dttm__gte, так как время с камер пишется в UTC+6
            mean_queue = CameraCashboxStat.objects.filter(
                camera_cashbox__cashbox_id=cashbox.id,
                dttm__gte=dttm_now - timedelta(seconds=100),
                dttm__lte=dttm_now + timedelta(seconds=60)
            ).aggregate(mean_queue=Avg('queue'))
            if mean_queue:
                try:
                    # todo fix this
                    mean_queue = round(mean_queue['mean_queue'], 1)
                except:
                    mean_queue = mean_queue['mean_queue']

        # todo: rewrite without 100500 requests to db (CameraCashboxStat also)
        status = WorkerDayCashboxDetails.objects.qos_filter_version(checkpoint).select_related('worker_day__worker').filter(
            on_cashbox=cashbox,
            dttm_to__isnull=True,
            worker_day__dt=(dttm_now-timedelta(hours=2)).date(),
            worker_day__worker__shop_id=shop_id,
        )

        user_id = None
        if not status:
            status = 'C'
        else:
            user_id = str(status[0].worker_day.worker_id)
            status = 'O'

        if cashbox.type.id not in response:
            response[cashbox.type.id] = {
                "name": cashbox.type.name,
                "priority": cashbox.type.priority,
                "with_queue": with_queue,
                "cashbox": []
            }

        response[cashbox.type.id]["cashbox"] += {
            "number": cashbox.number,
            "cashbox_id": cashbox.id,
            "status": status,

            "queue": mean_queue,
            "user_id": user_id,
        },

    return JsonResponse.success(response)


@api_method('GET', GetCashiersInfo)
def get_cashiers_info(request, form):
    """
    Показывает статусы всех кассиров работающих в данное время.

    Todo:
        Неправильно работает ползунок со временем (проблема скорее всего на бэке)
        Сделать без привязки к времени tm_to_show_all_workers.

    Args:
        method: GET
        url: /api/tablet/get_cashiers_info
        shop_id (int): required = False
        dttm (QOS_DATETIME): дата и время
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)

    Returns:
        {
            worker_id: {
                | 'break_triplets': [\n
                    [время в минутах сколько перерыв идет/был, 0/1 (перерыв был или нет)],
                    ...
                | ],
                | 'cashbox_dttm_added': время, когда была добавлена касса (либо null),
                | 'cashbox_dttm_deleted': время, когда была удалена касса (либо null),
                | 'cashbox_id': id кассы за которой сидит сотрудник, либо null (если сотрудник на перерыве, например),
                | 'cashbox_number': номер кассы, либо null,
                | 'cashbox_type': id типа касы за которой сегодня сотрудник работает,
                'cashbox_types': [
                    {
                        | 'bills_amount': количество чеков,
                        | 'cashbox_type: id типа кассы,
                        | 'id': id объекта WorkerCashboxInfo,
                        | 'mean_speed': средняя скорость,
                        | 'period': ,
                        | 'priority': ,
                        | 'worker': id работника
                    }
                ],\n
                | 'default_break_triplets' (str): "[15, 30, 15]", либо "[15, 30, 15, 15]" (например),
                | 'status': статус работника. например "W" -- работает, "B" -- перерыв
                | 'time_without_rest': количество минут которое сотрудник работает без перерыва(обнуляется после каждого перерыва),
                | 'dttm_work_end': дата-время, когда заканчивается рабочий день,
                | 'dttm_work_start': дата-время, когда начинается рабочий день,
                | 'worker_day_id': id соответствующего объекта worker_day,
                | 'worker_id': id работника
            }
        }

    """

    shop_id = FormUtil.get_shop_id(request, form)
    checkpoint = FormUtil.get_checkpoint(form)
    dttm = form['dttm']
    response = {}

    shop = Shop.objects.get(id=shop_id)
    break_triplets = shop.break_triplets
    list_of_break_triplets = json.loads(break_triplets)
    time_without_rest = {}

    status = WorkerDayCashboxDetails.objects.qos_filter_version(checkpoint).filter(
        worker_day__dttm_work_start__lte=dttm + timedelta(minutes=30),
        worker_day__dt=(dttm - timedelta(hours=2)).date(),
        worker_day__worker__shop__id=shop_id,
    ).order_by('id')

    for item in status:
        triplets = []
        default_break_triplets = []

        dttm_work_end = item.worker_day.dttm_work_end if item.worker_day.dttm_work_end else None
        dttm_work_start = item.worker_day.dttm_work_start if item.worker_day.dttm_work_start else None

        duration_of_work = round((dttm_work_end - dttm_work_start).total_seconds() / 60)

        if item.worker_day.worker_id not in time_without_rest.keys():
            time_without_rest[item.worker_day.worker_id] = 0

        for triplet in list_of_break_triplets:
            if float(triplet[0]) < duration_of_work <= float(triplet[1]):
                for time_triplet in triplet[2]:
                    triplets.append([0, 0])
                    default_break_triplets.append(time_triplet)

        if item.worker_day.dttm_work_start > dttm and item.worker_day.dt == dttm.date() and not item.is_tablet:
            item.status = WorkerDayCashboxDetails.TYPE_SOON
        else:
            if item.is_tablet is True:
                if item.status == WorkerDayCashboxDetails.TYPE_BREAK:
                    time_without_rest[item.worker_day.worker_id] = 0

                    if item.dttm_to is None:
                        break_end = dttm
                    else:
                        break_end = item.dttm_to

                    if item.dttm_from is None:
                        item.dttm_from = dttm
                    real_break_time = (break_end - item.dttm_from).total_seconds()

                    for triplet in list_of_break_triplets:
                        if int(triplet[0]) < duration_of_work <= int(triplet[1]):
                            if response.get(item.worker_day.worker_id):
                                triplets = response[item.worker_day.worker_id]['break_triplets']
                                for it in triplets:
                                    if it[1] == 0:
                                        if real_break_time >= 0:
                                            it[0] = round(float(real_break_time) / 60)
                                        it[1] = 1
                                        break
                                else:
                                    triplets.append([round(float(real_break_time)/60), 1])
                                    default_break_triplets.append(15)
                            break

                elif item.status == WorkerDayCashboxDetails.TYPE_WORK:

                    if item.dttm_to is None:
                        dttm_to = dttm
                    else:
                        dttm_to = item.dttm_to

                    time_without_rest[item.worker_day.worker_id] += round((dttm_to - item.dttm_from).total_seconds() / 60)

                if not item.dttm_to is None:
                    item.status = WorkerDayCashboxDetails.TYPE_FINISH
            else:
                item.status = WorkerDayCashboxDetails.TYPE_T

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
                "status": item.status,
                "worker_day_id": item.worker_day_id,
                "tm_work_start": str(item.dttm_from.time()),
                "tm_work_end": str(item.worker_day.dttm_work_end.time()),
                "default_break_triplets": str(default_break_triplets),
                "break_triplets": triplets,
                "cashbox_id": item.on_cashbox_id,
                "cashbox_dttm_added": cashbox_dttm_added,
                "cashbox_dttm_deleted": cashbox_dttm_deleted,
                "cashbox_type": cashbox_type,
                "cashbox_number": cashbox_number,
            }

        else:
            tm_work_end = item.dttm_to if item.status == WorkerDayCashboxDetails.TYPE_FINISH else item.worker_day.dttm_work_end
            if not item.on_cashbox_id is None:
                cashbox_type = item.cashbox_type_id
            else:
                cashbox_type = response[item.worker_day.worker_id]["cashbox_type"]

            response[item.worker_day.worker_id].update({
                "status": item.status,
                "cashbox_id": item.on_cashbox_id,
                "cashbox_dttm_added": cashbox_dttm_added,
                "cashbox_number": cashbox_number,
                "time_without_rest": time_without_rest[item.worker_day.worker_id],
                "default_break_triplets": str(default_break_triplets),
                "tm_work_end": str(tm_work_end.time()),
                "cashbox_type": cashbox_type,
            })

    user_ids = response.keys()
    worker_cashboxes_types = WorkerCashboxInfo.objects.select_related('cashbox_type').filter(worker_id__in=user_ids, is_active=True)
    worker_cashboxes_types = group_by(list(worker_cashboxes_types), group_key=lambda _: _.worker_id,)

    for user_id in response.keys():
        if user_id in worker_cashboxes_types.keys():
            response[user_id]['cashbox_types'] = [WorkerCashboxInfoConverter.convert(x) for x in worker_cashboxes_types.get(user_id)]

    return JsonResponse.success(response)


@api_method(
    'POST',
    ChangeCashierStatus,
    groups=[User.GROUP_MANAGER, User.GROUP_SUPERVISOR, User.GROUP_DIRECTOR],
    lambda_func=lambda x: User.objects.get(id=x['worker_id'])
)
def change_cashier_status(request, form):
    """
    Меняет статус кассира если это возможно.

    Args:
        method: POST
        url: api/tablet/change_cashier_status
        worker_id (int): required = True
        status (char): статус на который хотим поменять (например, "W", "H")
        cashbox_id (int): required = False. id кассы на которую хотим посадить (либо null если например отправляем работника домой)
        is_current_time (bool): когда приходит сотрудник ставить ему время прихода текущее (True), или по расписанию (False)
        tm_changin (QOS_TIME): required = False
        tm_work_end (QOS_TIME): required = False. Если сотрудник вышел не по расписанию, объекта workerday_cashbox_details у него
            на этот день нету, соответственно нужно проставить время окончания рабочего дня.
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)

    Returns:
        {
            | 'worker_id': id работяги,
            | 'status': новый статус пользователя,
            | 'cashbox_id': id кассы, либо null
        }

    Raises:
        JsonResponse.value_error в случаях, когда:
            Пытаемся поменять статус работника, который уже ушел домой или был отпущен. \n
            Пытаемся поменять статус на 'Скоро придет' \n
            Пытаемся посадить сотрудника на кассу, на которой уже кто-то работает \n


    """
    worker_id = form['worker_id']
    new_user_status = form['status']
    cashbox_id = form['cashbox_id']
    is_current_time = form['is_current_time']
    tm_work_end = form['tm_work_end']
    checkpoint = FormUtil.get_checkpoint(form)

    dttm_now = (now() + timedelta(hours=3)).replace(microsecond=0)
    dt = (dttm_now-timedelta(hours=3)).date()
    time = dttm_now.time() #if is_current_time else form['tm_changing']
    # todo: пока что так. потом исправить
    tm_work_end = tm_work_end if tm_work_end else (datetime.combine(dt, time) + timedelta(hours=9)).time()

    cashbox_id = cashbox_id if new_user_status == WorkerDayCashboxDetails.TYPE_WORK else None
    cashbox_type = None if cashbox_id is None else CashboxType.objects.get(cashbox__id=cashbox_id)
    wdcd = None

    workerday_detail_obj = WorkerDayCashboxDetails.objects.qos_filter_version(checkpoint).filter(
        worker_day__dt=dt,
        worker_day__worker_id=worker_id
    ).order_by('id').last()

    try:
        worker_day = WorkerDay.objects.qos_filter_version(checkpoint).get(dt=dt, worker_id=worker_id)
    except WorkerDay.DoesNotExist:
        return JsonResponse.does_not_exists_error()
    except WorkerDay.MultipleObjectsReturned:
        return JsonResponse.multiple_objects_returned()

    cashbox_worked = WorkerDayCashboxDetails.objects.qos_filter_version(checkpoint).filter(
        Q(dttm_to__isnull=True) | Q(dttm_to__gt=dttm_now),
        worker_day__dt=dt,
        is_tablet=True,
        dttm_from__lte=dttm_now,
        on_cashbox_id=cashbox_id,
        status=WorkerDayCashboxDetails.TYPE_WORK,
    ).count()
    if cashbox_worked:
        return JsonResponse.value_error('cashbox already opened')

    # todo: add other checks for change statuses
    if (new_user_status == WorkerDayCashboxDetails.TYPE_FINISH) and (worker_day.type == WorkerDay.Type.TYPE_ABSENSE):
        return JsonResponse.value_error('can not change the status to {}'.format(new_user_status))

    if new_user_status == WorkerDayCashboxDetails.TYPE_SOON:
        return JsonResponse.value_error('can not change the status to {}'.format(new_user_status))

    # if (new_user_status == WorkerDayCashboxDetails.TYPE_ABSENCE) and (workerday_detail.is_tablet == True):
    #     return JsonResponse.value_error(
    #         'can not change the status to {}'.format(new_user_status))

    if (not workerday_detail_obj is None) and (workerday_detail_obj.is_tablet is True) and \
            (workerday_detail_obj.dttm_to is None):
        workerday_detail_obj.dttm_to = dttm_now
        workerday_detail_obj.save()

    if new_user_status == WorkerDayCashboxDetails.TYPE_ABSENCE:
        worker_day.type = WorkerDay.Type.TYPE_ABSENSE.value
        worker_day.save()
    elif new_user_status == WorkerDayCashboxDetails.TYPE_FINISH:
        WorkerDayCashboxDetails.objects.qos_filter_version(checkpoint).filter(
            worker_day__dt=dt,
            worker_day__worker_id=worker_id,
            is_tablet=False,
        ).delete()
        # aa: already close workerday_detail
        # workerday_detail_obj.status = WorkerDayCashboxDetails.TYPE_FINISH
        # workerday_detail_obj.on_cashbox = None
        # workerday_detail_obj.save()
    elif new_user_status in WorkerDayCashboxDetails.DETAILS_TYPES_LIST:
        wdcd = WorkerDayCashboxDetails.objects.create(
            worker_day=worker_day,
            on_cashbox_id=cashbox_id,
            cashbox_type=cashbox_type,
            dttm_from=dttm_now,
            status=new_user_status,
            is_tablet=True,
        )

        if (new_user_status == WorkerDayCashboxDetails.TYPE_WORK) and (worker_day.type != WorkerDay.Type.TYPE_WORKDAY.value):
            worker_day.type = WorkerDay.Type.TYPE_WORKDAY.value
            worker_day.dttm_work_start.replace(hour=time.hour, minute=time.minute, second=time.second)
            worker_day.dttm_work_end.replace(hour=tm_work_end.hour, minute=tm_work_end.minute, second=tm_work_end.second)
            worker_day.save()
    else:
        return JsonResponse.value_error('can not change the status to {}'.format(new_user_status))

    return JsonResponse.success({
        worker_day.worker_id: {
            "worker_id": worker_day.worker_id,
            "status": new_user_status,
            "cashbox_id": None if wdcd is None else wdcd.on_cashbox_id
        }
    })

