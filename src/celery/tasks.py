from datetime import date, timedelta, datetime
import os

from django.db.models import Avg, Q
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


from src.main.timetable.worker_exchange.utils import search_candidates, send_noti2candidates
from src.main.operation_template.utils import build_period_clients

from src.timetable.models import (
    WorkType,
    WorkerDayCashboxDetails,
    WorkerCashboxInfo,
    ShopMonthStat,
    ExchangeSettings,
)
from src.base.models import (
    Shop,
    User,
)
from src.forecast.models import (
    OperationTemplate
)
from src.celery.celery import app
from django.core.mail import EmailMultiAlternatives
from src.conf.djconfig import EMAIL_HOST_USER

import time as time_in_secs


@app.task
def op_type_build_period_clients():
    dt_from = now().date() + timedelta(days = 2)
    dt_to = dt_from + timedelta(days=62)

    oper_templates = OperationTemplate.objects.filter(
        Q(dt_built_to__isnull=True) | Q(dt_built_to__lt=dt_to),
        dttm_deleted__isnull=True,
    )

    for ot in oper_templates:
        build_period_clients(ot, dt_to=dt_to)


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
                    'worker_day__employment',
                    'worker_day'
                ).filter(
                    status=WorkerDayCashboxDetails.TYPE_WORK,
                    work_type=work_type,
                    on_cashbox__isnull=False,
                    worker_day__dt__gte=prev_month,
                    worker_day__dt__lt=dt,
                    dttm_to__isnull=False,
                    worker_day__employment__dt_fired__isnull=True
                ).order_by('worker_day__employment', 'worker_day__dt')

                for detail in worker_day_cashbox_details:
                    if last_user is None:
                        last_work_type = work_type
                        last_user = detail.worker_day.employment

                    if last_user != detail.worker_day.worker:
                        update_duration(last_user, last_work_type, duration)
                        last_user = detail.worker_day.employment
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
def update_shop_stats(dt=None):
    if not dt:
        dt = date.today().replace(day=1)
    else:
        dt = dt.replace(day=1)
    shops = list(Shop.objects.filter(dttm_deleted__isnull=True, child__isnull=True))
    month_stats = list(ShopMonthStat.objects.filter(shop__in=shops, shop__child__isnull=True, dt=dt, status__in=[ShopMonthStat.READY, ShopMonthStat.NOT_DONE]))
    if len(shops) != len(month_stats):
        shops_with_stats = list(ShopMonthStat.objects.filter(
            shop__child__isnull=True,
            shop__in=shops, 
            dt=dt,
        ).values_list('shop_id', flat=True))
        ShopMonthStat.objects.bulk_create(
            [
                ShopMonthStat(
                    shop=shop,
                    dt=dt,
                    dttm_status_change=datetime.now(),
                )
                for shop in shops
                if shop.id not in shops_with_stats
            ]
        )
        # for shop in shops:
        #     if shop.id not in shops_with_stats:
        #         ShopMonthStat.objects.create(
        #             shop=shop,
        #             dt=dt,
        #             dttm_status_change=datetime.now(),
        #         )
        month_stats = list(ShopMonthStat.objects.filter(shop__in=shops, shop__child__isnull=True, dt=dt, status__in=[ShopMonthStat.READY, ShopMonthStat.NOT_DONE]))
    for month_stat in month_stats:
        stats = get_shop_stats(
            shop_id=month_stat.shop_id,
            form=dict(
                from_dt=month_stat.dt,
                to_dt=month_stat.dt + relativedelta(months=1, days=-1),
                work_type_ids=[]
            ),
            indicators_only=True
        )['indicators']
        month_stat.idle = stats['deadtime_part']
        month_stat.fot = stats['FOT']
        month_stat.workers_amount = stats['cashier_amount']
        month_stat.revenue = stats['revenue']
        month_stat.lack = stats['covering_part']
        month_stat.fot_revenue = stats['fot_revenue']
        month_stat.save()


@app.task
def update_shop_stats_2_months():
    dt = date.today().replace(day=1)
    update_shop_stats(dt=dt)
    update_shop_stats(dt=dt + relativedelta(months=1))


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
