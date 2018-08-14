import datetime
from src.main.tablet.utils import time_diff
import json

from django.db.models import Avg
from django.utils.timezone import now
from datetime import timedelta

from src.main.timetable.worker_exchange.utils import (
    get_init_params,
    has_deficiency
)

from src.db.models import (
    PeriodDemand,
    CashboxType,
    CameraCashboxStat,
    WorkerDayCashboxDetails,
    WorkerMonthStat,
    ProductionMonth,
    WorkerDay,
    Notifications,
    Shop,
    User
)

from src.celery.celery import app


@app.task
def update_queue(till_dttm=None):
    time_step = datetime.timedelta(seconds=1800)
    if till_dttm is None:
        till_dttm = now()

    cashbox_types = CashboxType.objects.filter(
        dttm_last_update_queue__isnull=False
    )
    for cashbox_type in cashbox_types:
        dif_time = till_dttm - cashbox_type.dttm_last_update_queue
        while dif_time > time_step:
            mean_queue = CameraCashboxStat.objects.filter(
                camera_cashbox__cashbox__type__id=cashbox_type.id,
                dttm__gte=cashbox_type.dttm_last_update_queue,
                dttm__lt=cashbox_type.dttm_last_update_queue + time_step
            ).values('camera_cashbox_id').annotate(mean_queue=Avg('queue')).filter(mean_queue__gte=0.6)

            if len(mean_queue):
                mean_queue = sum([el['mean_queue'] for el in mean_queue]) / len(mean_queue) * 1.4

                changed_amount = PeriodDemand.objects.filter(
                    dttm_forecast=cashbox_type.dttm_last_update_queue,
                    cashbox_type_id=cashbox_type.id,
                    type=PeriodDemand.Type.FACT.value
                ).update(queue_wait_length=mean_queue)
                if changed_amount == 0:
                    PeriodDemand.objects.create(
                        dttm_forecast=cashbox_type.dttm_last_update_queue,
                        clients=0,
                        products=0,
                        type=PeriodDemand.Type.FACT.value,
                        queue_wait_time=0,
                        queue_wait_length=mean_queue,
                        cashbox_type_id=cashbox_type.id
                    )

            cashbox_type.dttm_last_update_queue += time_step
            dif_time -= time_step
        cashbox_type.save()


@app.task
def release_all_workers():
    dttm_now = now() + datetime.timedelta(hours=3)
    worker_day_cashbox_objs = \
        WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
            worker_day__dt=dttm_now.date() - datetime.timedelta(days=1),
            tm_to__is_null=True
        )

    for obj in worker_day_cashbox_objs:
        obj.on_cashbox = None
        obj.tm_to = obj.worker_day.tm_work_end
        obj.save()


@app.task
def update_worker_month_stat():
    dt = now().date()
    if dt.month - 1 == 0:
        dt1 = datetime.date(year=dt.year - 1, month=12, day=1)
        dt2 = datetime.date(year=dt.year - 1, month=11, day=1)
    elif dt.month - 1 == 1:
        dt1 = datetime.date(year=dt.year, month=1, day=1)
        dt2 = datetime.date(year=dt.year - 1, month=12, day=1)
    else:
        dt1 = datetime.date(year=dt.year, month=dt.month - 1, day=1)
        dt2 = datetime.date(year=dt.year, month=dt.month - 2, day=1)
    last_user = ''
    last_month_stat = ''
    work_hours = 0
    work_days = 0
    product_month_1 = ProductionMonth.objects.filter(
        dt_first=datetime.date(year=dt1.year, month=dt1.month, day=dt1.day),
    )
    product_month_2 = ProductionMonth.objects.filter(
        dt_first=datetime.date(year=dt2.year, month=dt2.month, day=dt1.day),
    )
    shops = Shop.objects.all()
    for shop in shops:

        status = WorkerDay.objects.select_related('worker').filter(
            worker_shop=shop,
            dt__lte=datetime.date(year=dt.year, month=dt.month, day=1),
            dt__gte=dt2,
        ).order_by('worker', 'dt')

        break_triplets = shop.break_triplets
        list_of_break_triplets = json.loads(break_triplets)
        for item in status:

            time_break_triplets = 0
            duration_of_workerday = 0

            if item.tm_work_start and item.tm_work_end:
                duration_of_workerday = round(time_diff(item.tm_work_start, item.tm_work_end) / 60)
                for triplet in list_of_break_triplets:
                    if float(triplet[0]) < duration_of_workerday <= float(triplet[1]):

                        for time_triplet in triplet[2]:
                            time_break_triplets += time_triplet

            duration_of_workerday -= time_break_triplets
            if last_user and last_month_stat:
                if last_user.id == item.worker.id and last_month_stat == item.dt.month:
                    work_hours += round(duration_of_workerday / 60, 3)
                    if duration_of_workerday > 0:
                        work_days += 1
                else:
                    if last_month_stat == dt1.month:
                        product_month = product_month_1[0]
                    else:
                        product_month = product_month_2[0]
                    WorkerMonthStat.objects.update_or_create(
                        worker=last_user,
                        month=product_month,
                        defaults={
                            'work_days': work_days,
                            'work_hours': work_hours,
                        })

                    work_hours = round(duration_of_workerday / 60, 3)
                    if duration_of_workerday > 0:
                        work_days = 1
                    else:
                        work_days = 0
            else:
                work_hours = round(duration_of_workerday / 60, 3)
                if duration_of_workerday > 0:
                    work_days = 1
                else:
                    work_days = 0
            last_user = item.worker
            last_month_stat = item.dt.month
        if last_month_stat == dt1.month:
            product_month = product_month_1[0]
        else:
            product_month = product_month_2[0]
        if last_user:
            WorkerMonthStat.objects.update_or_create(
                worker=last_user,
                month=product_month,
                defaults={
                    'work_days': work_days,
                    'work_hours': work_hours,
                })
        last_user = ''
        last_month_stat = ''
        work_hours = 0
        work_days = 0


@app.task
def notify_cashiers_lack():
    for shop in Shop.objects.all():
        dttm_now = now()
        shop_id = shop.id

        init_params_dict = get_init_params(dttm_now, shop_id)

        return_dict = has_deficiency(
            init_params_dict['predict_demand'],
            init_params_dict['mean_bills_per_step'],
            init_params_dict['cashbox_types_hard_dict'],
            dttm_now
        )

        to_notify = False  # есть ли вообще нехватка
        notification_text = None  # {ct type : 'notification_text' or False если нет нехватки }
        for cashbox_type in return_dict.keys():
            if return_dict[cashbox_type]:
                to_notify = True
                notification_text =\
                'За типом кассы {} не хватает кассиров: {}. '.\
                format(
                    CashboxType.objects.get(id=cashbox_type).name,
                    return_dict[cashbox_type]
                )

        managers_lists = User.objects.filter(shop_id=shop_id, work_type=User.WorkType.TYPE_MANAGER.value)
        # если такого уведомления еще нет
        if to_notify:
            for manager in managers_lists:
                if not Notifications.objects.filter(
                        type=Notifications.TYPE_INFO,
                        to_worker=manager,
                        text=notification_text,
                        dttm_added__lt=now() + timedelta(hours=2)):  # повторить уведомление раз в час
                    Notifications.objects.create(
                        type=Notifications.TYPE_INFO,
                        to_worker=manager,
                        text=notification_text
                    )

