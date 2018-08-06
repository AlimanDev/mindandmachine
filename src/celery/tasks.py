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
    Notifications,
    Shop,
    User
    )
from src.celery.celery import app


@app.task
def update_queue(till_dttm=None):
    time_step = timedelta(seconds=1800)
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
    dttm_now = now() + timedelta(hours=3)
    worker_day_cashbox_objs = \
        WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
            worker_day__dt=dttm_now.date() - timedelta(days=1),
            tm_to__is_null=True
            )

    for obj in worker_day_cashbox_objs:
        obj.on_cashbox = None
        obj.tm_to = obj.worker_day.tm_work_end
        obj.save()


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
        notification_text = 'В данный момент не хватает '
        for cashbox_type in return_dict.keys():
            if return_dict[cashbox_type]:
                to_notify = True
                notification_text += '{} кассира '.format(return_dict[cashbox_type]) + \
                                     'за {} '.format(CashboxType.objects.get(id=cashbox_type).name)

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




