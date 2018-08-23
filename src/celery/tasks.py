import datetime
from src.main.tablet.utils import time_diff
import json

from django.db.models import Avg
from django.utils.timezone import now
from django.db.models import Q

from src.main.timetable.worker_exchange.utils import (
    get_init_params,
    has_deficiency
)
from src.main.demand.utils import create_predbills_request_function

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
    User,
    ProductionDay
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
        print('начал работать в функции update_queue')
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
    """
    отпускает всех работников с касс
    :return:
    """
    dttm_now = now() + datetime.timedelta(hours=3)
    worker_day_cashbox_objs = \
        WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
            worker_day__dt=dttm_now.date() - datetime.timedelta(days=1),
            tm_to__isnull=True
        )

    for obj in worker_day_cashbox_objs:
        obj.on_cashbox = None
        obj.tm_to = obj.worker_day.tm_work_end
        obj.save()

    print('отпустил всех домой')


@app.task
def update_worker_month_stat():
    dt = now().date().replace(day=1)
    delta = datetime.timedelta(days=20)
    dt1 = (dt - delta).replace(day=1)
    dt2 = (dt1 - delta).replace(day=1)
    product_month_1 = ProductionMonth.objects.get(
        dt_first=dt1,
    )
    product_month_2 = ProductionMonth.objects.get(
        dt_first=dt2,
    )
    shops = Shop.objects.all()
    for shop in shops:
        work_hours = 0
        work_days = 0
        print('начал обновлять worker month stat для {}'.format(shop))

        break_triplets = shop.break_triplets
        list_of_break_triplets = json.loads(break_triplets)
        time_break_triplets = 0
        for triplet in list_of_break_triplets:
            for time_triplet in triplet[2]:
                time_break_triplets += time_triplet
            triplet[2] = time_break_triplets
            time_break_triplets = 0

        worker_days = WorkerDay.objects.select_related('worker').filter(
            worker_shop=shop,
            dt__lt=dt,
            dt__gte=dt2,
        ).order_by('worker', 'dt')

        last_user = worker_days[0].worker if len(worker_days) else None
        last_month_stat = worker_days[0].dt.month if len(worker_days) else None
        product_month = product_month_1 if last_month_stat == dt1.month else product_month_2

        for worker_day in worker_days:
            time_break_triplets = 0
            duration_of_workerday = 0

            if worker_day.type in WorkerDay.TYPES_PAID:
                if worker_day.type != WorkerDay.Type.TYPE_WORKDAY.value and \
                        worker_day.type != WorkerDay.Type.TYPE_HOLIDAY_WORK.value:
                    duration_of_workerday = ProductionDay.WORK_NORM_HOURS[ProductionDay.TYPE_WORK]
                else:
                    duration_of_workerday = round(time_diff(worker_day.tm_work_start, worker_day.tm_work_end) / 3600, 3)

                    for triplet in list_of_break_triplets:
                        if float(triplet[0]) < duration_of_workerday * 60 <= float(triplet[1]):
                            time_break_triplets = triplet[2]
                    duration_of_workerday -= round(time_break_triplets / 60, 3)

            if last_user.id == worker_day.worker.id and last_month_stat == worker_day.dt.month:
                if worker_day.type in WorkerDay.TYPES_PAID:
                    work_days += 1
                    work_hours += duration_of_workerday
            else:
                WorkerMonthStat.objects.update_or_create(
                    worker=last_user,
                    month=product_month,
                    defaults={
                        'work_days': work_days,
                        'work_hours': work_hours,
                    })

                work_hours = duration_of_workerday
                work_days = 1 if worker_day.type in WorkerDay.TYPES_PAID else 0
                last_user = worker_day.worker
                last_month_stat = worker_day.dt.month
                product_month = product_month_1 if last_month_stat == dt1.month else product_month_2

        if last_user:
            WorkerMonthStat.objects.update_or_create(
                worker=last_user,
                month=product_month,
                defaults={
                    'work_days': work_days,
                    'work_hours': work_hours,
                })


@app.task
def notify_cashiers_lack():
    """
    creates notification if there's deficiency of cashiers for each shop
    :return:
    """
    for shop in Shop.objects.all():
        dttm_now = now()
        notify_to = dttm_now + datetime.timedelta(days=7)
        shop_id = shop.id
        dttm = dttm_now
        while dttm <= notify_to:
            init_params_dict = get_init_params(dttm, shop_id)

            return_dict = has_deficiency(
                init_params_dict['predict_demand'],
                init_params_dict['mean_bills_per_step'],
                init_params_dict['cashbox_types_hard_dict'],
                dttm
            )

            to_notify = False  # есть ли вообще нехватка
            notification_text = None  # {ct type : 'notification_text' or False если нет нехватки }
            for cashbox_type in return_dict.keys():
                if return_dict[cashbox_type]:
                    to_notify = True
                    notification_text = '{}.{} в {}-{} за типом кассы {} не будет хватать кассиров: {}. '.format(
                        dttm.day, dttm.month, dttm.hour, dttm.minute,
                        CashboxType.objects.get(id=cashbox_type).name,
                        return_dict[cashbox_type]
                    )

            managers_dir_list = User.objects.filter(Q(group=User.GROUP_SUPERVISOR) | Q(group=User.GROUP_MANAGER), shop_id=shop_id)
            notifications_list = []
            users_with_such_notes = []

            notes = Notifications.objects.filter(
                type=Notifications.TYPE_INFO,
                text=notification_text,
                dttm_added__lt=now() + datetime.timedelta(hours=2)
            )
            for note in notes:
                users_with_such_notes.append(note.to_worker_id)

            if to_notify:
                for recipient in managers_dir_list:
                    if recipient.id not in users_with_such_notes:
                        notifications_list.append(
                            Notifications(
                                type=Notifications.TYPE_INFO,
                                to_worker=recipient,
                                text=notification_text,
                            )
                        )
            dttm += datetime.timedelta(minutes=30)
            Notifications.objects.bulk_create(notifications_list)
    print('уведомил о нехватке')


@app.task
def create_pred_bills():
    # todo: подумать, мб есть более красивый способ, чем задавать default_dt
    for shop in Shop.objects.all():
        create_predbills_request_function(shop.id)
    print('создал спрос на месяц')
