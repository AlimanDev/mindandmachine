import datetime
import json

from django.db.models import Avg
from django.utils.timezone import now
from dateutil.relativedelta import relativedelta
from django.db.models import Q

from src.main.timetable.worker_exchange.utils import (
    get_init_params,
    has_deficiency
)
from src.main.demand.utils import create_predbills_request_function

from src.db.models import (
    PeriodQueues,
    CashboxType,
    CameraCashboxStat,
    WorkerDayCashboxDetails,
    WorkerMonthStat,
    ProductionMonth,
    WorkerDay,
    Notifications,
    Shop,
    User,
    ProductionDay,
    WorkerCashboxInfo,
)
from src.celery.celery import app


@app.task
def update_queue(till_dttm=None):
    """
    Обновляет данные по очереди на всех типах касс

    Args:
        till_dttm(datetime.datetime): до какого времени обновлять?

    Note:
        Выполняется каждые полчаса
    """
    time_step = datetime.timedelta(seconds=1800)
    if till_dttm is None:
        till_dttm = now()

    cashbox_types = CashboxType.objects.filter(
        dttm_last_update_queue__isnull=False,
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

                changed_amount = PeriodQueues.objects.filter(
                    dttm_forecast=cashbox_type.dttm_last_update_queue,
                    cashbox_type_id=cashbox_type.id,
                    type=PeriodQueues.FACT_TYPE,
                ).update(value=mean_queue)
                if changed_amount == 0:
                    PeriodQueues.objects.create(
                        dttm_forecast=cashbox_type.dttm_last_update_queue,
                        type=PeriodQueues.FACT_TYPE,
                        value=mean_queue,
                        cashbox_type_id=cashbox_type.id,
                    )

            cashbox_type.dttm_last_update_queue += time_step
            dif_time -= time_step
        cashbox_type.save()


@app.task
def release_all_workers():
    """
    Отпускает всех работников с касс

    Note:
        Выполняется каждую ночь
    """

    dttm_now = now() + datetime.timedelta(hours=3)
    worker_day_cashbox_objs = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
        worker_day__dt=dttm_now.date() - datetime.timedelta(days=1),
        dttm_to__isnull=True,
    )


    for obj in worker_day_cashbox_objs:
        obj.on_cashbox = None
        obj.dttm_to = obj.worker_day.dttm_work_end
        obj.save()

    print('отпустил всех домой')


@app.task
def update_worker_month_stat():
    """
    Обновляет данные по рабочим дням и часам сотрудников

    Note:
        Обновляется 1 и 15 числа каждого месяца
    """
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
        # print('начал обновлять worker month stat для {}'.format(shop))

        break_triplets = shop.break_triplets
        list_of_break_triplets = json.loads(break_triplets)
        time_break_triplets = 0
        for triplet in list_of_break_triplets:
            for time_triplet in triplet[2]:
                time_break_triplets += time_triplet
            triplet[2] = time_break_triplets
            time_break_triplets = 0

        worker_days = WorkerDay.objects.qos_current_version().select_related('worker').filter(
            worker__shop=shop,
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
                    duration_of_workerday = round((worker_day.dttm_work_end - worker_day.dttm_work_start)
                                                  .total_seconds() / 3600, 3)

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
    Создает уведомления на неделю вперед, если в магазине будет нехватка кассиров

    Note:
        Выполняется каждую ночь
    """
    for shop in Shop.objects.all():
        dttm_now = now()
        notify_to = dttm_now + datetime.timedelta(days=7)
        shop_id = shop.id
        dttm = datetime.datetime.combine(
            dttm_now.date(),
            datetime.time(dttm_now.hour, 0 if dttm_now.minute < 30 else 30, 0)
        )
        init_params_dict = get_init_params(dttm_now, shop_id)
        cashbox_types = init_params_dict['cashbox_types_dict']
        period_demands = init_params_dict['predict_demand']
        mean_bills_per_step = init_params_dict['mean_bills_per_step']
        # пока что есть магазы в которых нет касс с ForecastHard
        if cashbox_types and period_demands:
            return_dict = has_deficiency(
                period_demands,
                mean_bills_per_step,
                cashbox_types,
                dttm,
                notify_to
            )

            notifications_list = []
            for dttm_converted in return_dict.keys():
                to_notify = False  # есть ли вообще нехватка
                hrs, minutes, other = dttm_converted.split(':')
                notification_text = '{}:{} {}:\n'.format(hrs, minutes, other[3:])
                if return_dict[dttm_converted]:
                    to_notify = True
                    for cashbox_type in return_dict[dttm_converted].keys():
                        if return_dict[dttm_converted][cashbox_type]:
                            notification_text += '{} будет не хватать сотрудников: {}. '.format(
                                CashboxType.objects.get(id=cashbox_type).name,
                                return_dict[dttm_converted][cashbox_type]
                            )
                    managers_dir_list = User.objects.filter(Q(group=User.GROUP_SUPERVISOR) | Q(group=User.GROUP_MANAGER), shop_id=shop_id)
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

            Notifications.objects.bulk_create(notifications_list)

    print('уведомил о нехватке')


@app.task
def allocation_of_time_for_work_on_cashbox():
    """
    Update the number of worked hours last month for each user in WorkerCashboxInfo
    """

    def update_duration(last_user, last_cashbox_type, duration):
        WorkerCashboxInfo.objects.filter(
            worker=last_user,
            cashbox_type=last_cashbox_type,
        ).update(duration=round(duration, 3))

    dt = now().date().replace(day=1)

    delta = datetime.timedelta(days=20)
    prev_month = (dt - delta).replace(day=1)
    shops = Shop.objects.all()

    for shop in shops:
        # Todo: может нужно сделать qos_filter на типы касс?
        cashbox_types = CashboxType.objects.filter(shop=shop)
        last_user = None
        last_cashbox_type = None
        duration = 0

        if len(cashbox_types):
            for cashbox_type in cashbox_types:
                worker_day_cashbox_details = WorkerDayCashboxDetails.objects.select_related(
                    'worker_day__worker',
                    'worker_day'
                ).filter(
                    status=WorkerDayCashboxDetails.TYPE_WORK,
                    cashbox_type=cashbox_type,
                    on_cashbox__isnull=False,
                    worker_day__dt__gte=prev_month,
                    worker_day__dt__lt=dt,
                    dttm_to__isnull=False,
                    is_tablet=True,
                ).order_by('worker_day__worker')

                for detail in worker_day_cashbox_details:

                    if last_user is None:
                        last_cashbox_type = cashbox_type
                        last_user = detail.worker_day.worker

                    if last_user != detail.worker_day.worker:
                        update_duration(last_user, last_cashbox_type, duration)
                        last_user = detail.worker_day.worker
                        last_cashbox_type = cashbox_type
                        duration = 0

                    duration += (detail.dttm_to - detail.dttm_from).total_seconds() / 3600

            if last_user:
                update_duration(last_user, last_cashbox_type, duration)


@app.task
def create_pred_bills():
    """
    Обновляет данные по спросу

    Note:
        Выполняется первого числа каждого месяца
    """
    for shop in Shop.objects.all():
        create_predbills_request_function(shop.id)
    print('создал спрос на месяц')


@app.task
def clean_camera_stats():
    """
    Удаляет данные с камер за последние for_past_months месяцев

    Note:
        Запускается раз в неделю
    """
    for_past_months = 3
    dttm_to_delete = now() - relativedelta(months=for_past_months)

    CameraCashboxStat.objects.filter(dttm__lt=dttm_to_delete).delete()
