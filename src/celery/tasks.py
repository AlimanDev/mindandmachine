from datetime import date, timedelta
import json
import os

from django.db.models import Avg
from django.utils.timezone import now
from dateutil.relativedelta import relativedelta
from src.main.upload.utils import upload_demand_util, upload_employees_util, upload_vacation_util, sftp_download

from src.main.timetable.worker_exchange.utils import (
    # get_init_params,
    # has_deficiency,
    # split_cashiers_periods,
    # intervals_to_shifts,
    search_candidates,
    send_noti2candidates,
    cancel_vacancy,
    confirm_vacancy,
    create_vacancies_and_notify,
    cancel_vacancies,
    workers_exchange
)

from src.main.demand.utils import create_predbills_request_function
from src.main.timetable.cashier_demand.utils import get_worker_timetable2 as get_shop_stats
from src.db.models import (
    Event,
    PeriodQueues,
    WorkType,
    CameraCashboxStat,
    WorkerDayCashboxDetails,
    WorkerMonthStat,
    ProductionMonth,
    WorkerDay,
    # Notifications,
    Shop,
    User,
    ProductionDay,
    WorkerCashboxInfo,
    CameraClientGate,
    CameraClientEvent,
    Timetable,
    IncomeVisitors,
    EmptyOutcomeVisitors,
    PurchasesOutcomeVisitors,
    ExchangeSettings,
)
from src.celery.celery import app
<<<<<<< HEAD
from django.core.mail import EmailMultiAlternatives
from src.conf.djconfig import EMAIL_HOST_USER

=======
import time as time_in_secs
>>>>>>> master

@app.task
def update_queue(till_dttm=None):
    """
    Обновляет данные по очереди на всех типах касс

    Args:
        till_dttm(datetime.datetime): до какого времени обновлять?

    Note:
        Выполняется каждые полчаса
    """
    time_step = timedelta(seconds=1800)  # todo: change to supershop step
    if till_dttm is None:
        till_dttm = now() + timedelta(hours=3)  # moscow time

    work_types = WorkType.objects.qos_filter_active(till_dttm + timedelta(minutes=30), till_dttm).filter(
        dttm_last_update_queue__isnull=False,
    )
    if not len(work_types):
        raise ValueError('WorkType EmptyQuerySet with dttm_last_update_queue')
    for work_type in work_types:
        dif_time = till_dttm - work_type.dttm_last_update_queue
        while dif_time > time_step:
            mean_queue = list(CameraCashboxStat.objects.filter(
                camera_cashbox__cashbox__type__id=work_type.id,
                dttm__gte=work_type.dttm_last_update_queue,
                dttm__lt=work_type.dttm_last_update_queue + time_step
            ).values('camera_cashbox_id').annotate(mean_queue=Avg('queue')).values_list('mean_queue', flat=True)) #.filter(mean_queue__gte=0.5)
            # todo: mean_queue__gte seems stupid -- need to change and look only open

            if len(mean_queue):

                min_possible_period_len = max(mean_queue) * 0.17
                mean_queue = list([el for el in mean_queue if el > min_possible_period_len and el > 0.4])
                mean_queue = sum(mean_queue) / (len(mean_queue) + 0.000001)

                changed_amount = PeriodQueues.objects.filter(
                    dttm_forecast=work_type.dttm_last_update_queue,
                    operation_type_id=work_type.work_type_reversed.all()[0].id,
                    type=PeriodQueues.FACT_TYPE,
                ).update(value=mean_queue)
                if changed_amount == 0:
                    PeriodQueues.objects.create(
                        dttm_forecast=work_type.dttm_last_update_queue,
                        type=PeriodQueues.FACT_TYPE,
                        value=mean_queue,
                        operation_type_id=work_type.work_type_reversed.all()[0].id,
                    )

            work_type.dttm_last_update_queue += time_step
            dif_time -= time_step
        work_type.save()


@app.task
def update_visitors_info():
    timestep = timedelta(minutes=30)
    dttm_now = now()
    # todo: исправить потом. пока делаем такую привязку
    # вообще хорошей идеей наверное будет просто cashbox_type blank=True, null=True сделать в PeriodDemand
    try:
        work_type = WorkType.objects.get(name='Кассы', shop_id=1)
    except WorkType.DoesNotExist:
        raise ValueError('Такого типа касс нет в базе данных.')
    create_dict = {
        'work_type': work_type,
        'dttm_forecast': dttm_now.replace(minute=(0 if dttm_now.minute < 30 else 30), second=0, microsecond=0),
        'type': IncomeVisitors.FACT_TYPE
    }

    events_qs = CameraClientEvent.objects.filter(
        dttm__gte=dttm_now - timestep,
        dttm__lte=dttm_now
    )

    income_visitors_value = events_qs.filter(
        gate__type=CameraClientGate.TYPE_ENTRY,
        type=CameraClientEvent.TYPE_TOWARD,
    ).count()
    empty_outcome_visitors_value = events_qs.filter(
        gate__type=CameraClientGate.TYPE_ENTRY,
        type=CameraClientEvent.TYPE_BACKWARD,
    ).count()
    purchases_outcome_visitors_value = events_qs.filter(
        gate__type=CameraClientGate.TYPE_OUT,
        type=CameraClientEvent.TYPE_TOWARD,
    ).count() - events_qs.filter(
        gate__type=CameraClientGate.TYPE_OUT,
        type=CameraClientEvent.TYPE_BACKWARD,
    ).count()

    IncomeVisitors.objects.create(
        value=income_visitors_value,
        **create_dict
    )
    EmptyOutcomeVisitors.objects.create(
        value=empty_outcome_visitors_value,
        **create_dict
    )
    PurchasesOutcomeVisitors.objects.create(
        value=purchases_outcome_visitors_value,
        **create_dict
    )

    print('успешно создал стату по покупателям')


@app.task
def release_all_workers():
    """
    Отпускает всех работников с касс

    Note:
        Выполняется каждую ночь
    """
    worker_day_cashbox_objs = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
        dttm_to__isnull=True,
    )

    for obj in worker_day_cashbox_objs:
        obj.on_cashbox = None
        obj.dttm_to = obj.worker_day.dttm_work_end
        obj.save()


@app.task
def update_worker_month_stat():
    """
    Обновляет данные по рабочим дням и часам сотрудников

    Note:
        Обновляется 1 и 15 числа каждого месяца
    """
    dt = now().date().replace(day=1)
    delta = timedelta(days=20)
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

# @app.task
# def notify_cashiers_lack():
#     """
#     Создает уведомления на неделю вперед, если в магазине будет нехватка кассиров
#
#     Note:
#         Выполняется каждую ночь
#     """
#     for shop in Shop.objects.all():
#         dttm_now = now()
#         notify_days = 7
#         dttm = dttm_now.replace(minute=0, second=0, microsecond=0)
#         init_params_dict = get_init_params(dttm_now, shop.id)
#         work_types = init_params_dict['work_types_dict']
#         mean_bills_per_step = init_params_dict['mean_bills_per_step']
#         period_demands = []
#         for i in range(notify_days):
#             period_demands += get_init_params(dttm_now + datetime.timedelta(days=i), shop.id)['predict_demand']
#
#         managers_dir_list = []
#         users_with_such_notes = []
#         # пока что есть магазы в которых нет касс с ForecastHard
#         if work_types and period_demands:
#             return_dict = has_deficiency(
#                 period_demands,
#                 mean_bills_per_step,
#                 work_types,
#                 dttm,
#                 dttm_now + datetime.timedelta(days=notify_days)
#             )
#             notifications_list = []
#             for dttm_converted in return_dict.keys():
#                 to_notify = False  # есть ли вообще нехватка
#                 hrs, minutes, other = dttm_converted.split(':')  # дропаем секунды
#                 if not shop.super_shop.is_supershop_open_at(datetime.time(hour=int(hrs), minute=int(minutes), second=0)):
#                     continue
#                 if sum(return_dict[dttm_converted].values()) > 0:
#                     to_notify = True
#                     notification_text = '{}:{} {}:\n'.format(hrs, minutes, other[3:])
#                     for work_type in return_dict[dttm_converted].keys():
#                         if return_dict[dttm_converted][work_type]:
#                             notification_text += '{} будет не хватать сотрудников: {}. '.format(
#                                 WorkType.objects.get(id=work_type).name,
#                                 return_dict[dttm_converted][work_type]
#                             )
#                     managers_dir_list = User.objects.filter(
#                         function_group__allowed_functions__func='get_workers_to_exchange',
#                         dt_fired__isnull=True,
#                         shop_id=shop.id
#                     )
#                     users_with_such_notes = []
#
# # TODO: REWRITE WITH EVENT
# # FIXME: REWRITE WITH EVENT
#                     # notes = Notifications.objects.filter(
#                     #     type=Notifications.TYPE_INFO,
#                     #     text=notification_text,
#                     #     dttm_added__lt=now() + datetime.timedelta(hours=2)
#                     # )
#                     # for note in notes:
#                     #     users_with_such_notes.append(note.to_worker_id)
#
#             #     if to_notify:
#             #         for recipient in managers_dir_list:
#             #             if recipient.id not in users_with_such_notes:
#             #                 notifications_list.append(
#             #                     Notifications(
#             #                         type=Notifications.TYPE_INFO,
#             #                         to_worker=recipient,
#             #                         text=notification_text,
#             #                     )
#             #                 )
#             #
#             # Notifications.objects.bulk_create(notifications_list)




@app.task
def vacancies_create_and_cancel():
    """
    Создает уведомления на неделю вперед, если в магазине будет нехватка кассиров

    """

    exchange_settings = ExchangeSettings.objects.first()
    if not exchange_settings.automatic_check_lack:
        return

    for shop in Shop.objects.all():
        for work_type in shop.worktype_set.all():
            cancel_shop_vacancies.apply_async((shop.id, work_type.id))
            create_shop_vacancies_and_notify.apply_async((shop.id, work_type.id))


@app.task
def create_shop_vacancies_and_notify(shop_id, work_type_id):
    """
    Создает уведомления на неделю вперед, если в магазине будет нехватка кассиров

    """

    create_vacancies_and_notify(shop_id, work_type_id)


@app.task
def cancel_shop_vacancies(shop_id, work_type_id):
    """
    Автоматически отменяем вакансии, в которых нет потребности
    :return:
    """
    cancel_vacancies(shop_id, work_type_id)


@app.task
def workers_hard_exchange():
    """

    Автоматически перекидываем сотрудников из других магазинов, если
    в том магазине потребность в сотруднике < 20%.

    :return:
    """
    workers_exchange()


# TODO: REWRITE WITH EVENT
# FIXME: REWRITE WITH EVENT
                    # notes = Notifications.objects.filter(
                    #     type=Notifications.TYPE_INFO,
                    #     text=notification_text,
                    #     dttm_added__lt=now() + datetime.timedelta(hours=2)
                    # )
                    # for note in notes:
                    #     users_with_such_notes.append(note.to_worker_id)

            #     if to_notify:
            #         for recipient in managers_dir_list:
            #             if recipient.id not in users_with_such_notes:
            #                 notifications_list.append(
            #                     Notifications(
            #                         type=Notifications.TYPE_INFO,
            #                         to_worker=recipient,
            #                         text=notification_text,
            #                     )
            #                 )
            #
            # Notifications.objects.bulk_create(notifications_list)


@app.task
def allocation_of_time_for_work_on_cashbox():
    """
    Update the number of worked hours last month for each user in WorkerCashboxInfo
    """

    def update_duration(last_user, last_work_type, duration):
        WorkerCashboxInfo.objects.filter(
            worker=last_user,
            work_type=last_work_type,
        ).update(duration=round(duration, 3))

    dt = now().date().replace(day=1)
    prev_month = dt - relativedelta(months=1)

    for shop in Shop.objects.all():
        work_types = WorkType.objects.qos_filter_active(
            dt_from=prev_month,
            dt_to=dt,
            shop=shop
        )
        last_user = None
        last_work_type = None
        duration = 0

        if len(work_types):
            for work_type in work_types:
                worker_day_cashbox_details = WorkerDayCashboxDetails.objects.select_related(
                    'worker_day__worker',
                    'worker_day'
                ).filter(
                    status=WorkerDayCashboxDetails.TYPE_WORK,
                    work_type=work_type,
                    on_cashbox__isnull=False,
                    worker_day__dt__gte=prev_month,
                    worker_day__dt__lt=dt,
                    dttm_to__isnull=False,
                    worker_day__worker__dt_fired__isnull=True
                ).order_by('worker_day__worker', 'worker_day__dt')

                for detail in worker_day_cashbox_details:
                    if last_user is None:
                        last_work_type = work_type
                        last_user = detail.worker_day.worker

                    if last_user != detail.worker_day.worker:
                        update_duration(last_user, last_work_type, duration)
                        last_user = detail.worker_day.worker
                        last_work_type = work_type
                        duration = 0

                    duration += (detail.dttm_to - detail.dttm_from).total_seconds() / 3600

            if last_user:
                update_duration(last_user, last_work_type, duration)


@app.task
def create_pred_bills():
    """
    Обновляет данные по спросу

    Note:
        Выполняется первого числа каждого месяца
    """
    # todo: переписать
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


@app.task
def update_shop_stats(dt=None):
    if not dt:
        dt = date.today().replace(day=1)
    shops = Shop.objects.filter(dttm_deleted__isnull=True)
    tts = Timetable.objects.filter(shop__in=shops, dt__gte=dt, status=Timetable.Status.READY.value)
    for timetable in tts:
        stats = get_shop_stats(
            shop_id=timetable.shop_id,
            form=dict(
                from_dt=timetable.dt,
                to_dt=timetable.dt + relativedelta(months=1, days=-1),
                work_type_ids=[]
            ),
            indicators_only=True
        )['indicators']
        timetable.idle = stats['deadtime_part']
        timetable.fot = stats['FOT']
        timetable.workers_amount = stats['cashier_amount']
        timetable.revenue = stats['revenue']
        timetable.lack = stats['covering_part']
        timetable.fot_revenue = stats['fot_revenue']
        timetable.save()


@app.task
def send_notify_email(message, send2user_ids, title=None, file=None, html_content=None):
    '''
    Функция-обёртка для отправки email сообщений (в том числе файлов)
    :param message: сообщение
    :param send2user_ids: список id пользователей
    :param title: название сообщения
    :param file: файл
    :param html_content: контент в формате html
    :return:
    '''

    # todo: add message if no emails
    user_emails = [user.email for user in User.objects.filter(id__in=send2user_ids) if user.email]
    msg = EmailMultiAlternatives(
        subject='Сообщение от Mind&Machine' if title is None else title,
        body=message,
        from_email=EMAIL_HOST_USER,
        to=user_emails,
    )
    if file:
        msg.attach_file(file)

    if html_content:
        msg.attach_alternative(html_content, "text/html")
    result = msg.send()
    return 'Отправлено {} сообщений из {}'.format(result, len(send2user_ids))


@app.task
def upload_demand_task():
    localpaths = [
        'bills_{}.csv'.format(str(time_in_secs.time()).replace('.', '_')),
        'incoming_{}.csv'.format(str(time_in_secs.time()).replace('.', '_'))
    ]
    for localpath in localpaths:
        sftp_download(localpath)
        file = open(localpath, 'r')
        upload_demand_util(file)
        file.close()
        os.remove(localpath)


@app.task
def upload_employees_task():
    localpath = 'employees_{}.csv'.format(str(time_in_secs.time()).replace('.', '_'))
    sftp_download(localpath)
    file = open(localpath, 'r')
    upload_employees_util(file)
    file.close()
    os.remove(localpath)


@app.task
def upload_vacation_task():
    localpath = 'holidays_{}.csv'.format(str(time_in_secs.time()).replace('.', '_'))
    sftp_download(localpath)
    file = open(localpath, 'r')
    upload_vacation_util(file)
    file.close()
    os.remove(localpath)

