import json
import logging
import os
import time as time_in_secs
from datetime import date, timedelta, datetime

import pandas as pd
import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.utils.timezone import now
from src.main.demand.utils import create_predbills_request_function
from src.main.operation_template.utils import build_period_clients
from src.main.upload.utils import upload_demand_util, upload_employees_util, upload_vacation_util, sftp_download

from src.base.message import Message
from src.base.models import (
    Shop,
    User,
    Notification,
    Subscribe,
    Event,
    Network,
)
from src.celery.celery import app
from src.conf.djconfig import EMAIL_HOST_USER
from src.forecast.load_template.utils import calculate_shop_load, apply_load_template
from src.forecast.models import (
    OperationTemplate,
    LoadTemplate,
    PeriodClients,
    Receipt,
    OperationType,
    OperationTypeName
)
from src.util.urv.create_urv_stat import main as create_urv
from src.conf.djconfig import URV_STAT_EMAILS, URV_STAT_SHOP_LEVEL
from src.timetable.models import (
    WorkType,
    WorkerDayCashboxDetails,
    EmploymentWorkType,
    ShopMonthStat,
    ExchangeSettings,
)
from src.timetable.vacancy.utils import (
    create_vacancies_and_notify,
    cancel_vacancies,
    workers_exchange,
)
from src.timetable.work_type.utils import get_efficiency as get_shop_stats


@app.task
def create_notifications_for_event(event_id):
    event = Event.objects.get(id=event_id)
    subscribes = Subscribe.objects.filter(type=event.type, shop=event.shop)
    notification_list = []
    for subscribe in subscribes:
        notification_list.append(
            Notification(
                worker=subscribe.user,
                event=event
            )
        )
        print(f"Create notification for {subscribe.user}, {event}")
    Notification.objects.bulk_create(notification_list)

@app.task
def create_notifications_for_subscribe(subscribe_id):
    subscribe = Subscribe.objects.get(id=subscribe_id)
    events = Event.objects.filter(shop=subscribe.shop, type=subscribe.type, dttm_valid_to__gte=now())
    notification_list = []
    for event in events:
        notification_list.append(
            Notification(
                worker=subscribe.user,
                event=event
            )
        )
        print(f"Create notification for {subscribe.user}, {event}")
        Notification.objects.bulk_create(notification_list)


@app.task
def delete_notifications():
    Event.objects.filter(
        dttm_valid_to__lte=now()
    ).delete()


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
    Создание вакансий для всех магазинов
    """

    exchange_settings_network = {
        e.network_id: e
        for e in ExchangeSettings.objects.filter(shops__isnull=True)
    }

    # exchange_settings = ExchangeSettings.objects.first()
    # if not exchange_settings.automatic_check_lack:
    #     return

    for shop in Shop.objects.select_related('exchange_settings').all():
        exchange_settings = shop.exchange_settings or exchange_settings_network.get(shop.network_id)
        if exchange_settings == None or not exchange_settings.automatic_check_lack:
            continue

        for work_type in shop.worktype_set.all():
            cancel_shop_vacancies.apply_async((shop.id, work_type.id))
            create_shop_vacancies_and_notify.apply_async((shop.id, work_type.id))


@app.task
def create_shop_vacancies_and_notify(shop_id, work_type_id):
    """
    Создание вакансий для магазина
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
        EmploymentWorkType.objects.filter(
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
    month_stats = list(ShopMonthStat.objects.filter(shop__in=shops, shop__child__isnull=True, dt=dt))
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
        month_stats = list(ShopMonthStat.objects.filter(shop__in=shops, shop__child__isnull=True, dt=dt))
    for month_stat in month_stats:
        # if month_stat.status not in [ShopMonthStat.READY, ShopMonthStat.NOT_DONE]:
        #     continue

        if settings.UPDATE_SHOP_STATS_WORK_TYPES_CODES:
            work_type_ids = list(month_stat.shop.worktype_set.filter(
                work_type_name__code__in=settings.UPDATE_SHOP_STATS_WORK_TYPES_CODES,
            ).values_list('id', flat=True))
        else:
            work_type_ids = []
        stats = get_shop_stats(
            shop_id=month_stat.shop_id,
            form=dict(
                from_dt=month_stat.dt,
                to_dt=month_stat.dt + relativedelta(months=1, days=-1),
                work_type_ids=work_type_ids,
                indicators=True,
                efficiency=False,
            ),
        )['indicators']
        month_stat.idle = stats['deadtime']
        month_stat.fot = stats['fot']
        month_stat.lack = stats['covering']  # на самом деле покрытие
        month_stat.predict_needs = stats['predict_needs']
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


@app.task
def calculate_shops_load(lang, load_template_id, dt_from, dt_to, shop_id=None):
    load_template = LoadTemplate.objects.get(pk=load_template_id)
    root_shop = Shop.objects.filter(level=0).first()
    shops = [load_template.shops.get(pk=shop_id)] if shop_id else load_template.shops.all()
    for shop in shops:
        res = calculate_shop_load(shop, load_template, dt_from, dt_to, lang=lang)
        if res['error']:
            event = Event.objects.create(
                type="load_template_err",
                params={
                    'shop': shop,
                    'message': Message(lang=lang).get_message(res['code'], params=res.get('params', {})),
                },
                dttm_valid_to=datetime.now() + timedelta(days=2),
                shop=root_shop,
            )
            create_notifications_for_event(event.id)


@app.task
def apply_load_template_to_shops(load_template_id, dt_from, shop_id=None):
    load_template = LoadTemplate.objects.get(pk=load_template_id)
    shops = [Shop.objects.get(pk=shop_id)] if shop_id else load_template.shops.all()
    for shop in shops:
        apply_load_template(load_template_id, shop.id, dt_from)
    event = Event.objects.create(
        type="load_template_apply",
        params={
            'name': load_template.name,
        },
        dttm_valid_to=datetime.now() + timedelta(days=2),
        shop=Shop.objects.filter(level=0).first(),
    )
    create_notifications_for_event(event.id)


'''
Исходные данные хранятся в виде json в базе данных. как именно агреггировать network.settings_values['receive_data_info']
представлен в виде списка, каждый элемент состоит из:

{
        'update_gap': промежуток времени для обновления (сколько последних дней обновляем),
        'delete_gap': промежуток времени для хранения данных (сколько последних дней храним в базе данных),
        'grouping_period':  промежуток времени, по которому группировать значения,
        'aggregate': [
            {
                'timeserie_code': код операции,
                'timeserie_action': ['count', 'sum'],
                'timeserie_value': какое значение для агрегации использовать,
                # 'timeserie_filters': словарь какие поля, какие значения должны иметь, # todo: круто бы добавить
            },
            ...
        ],
        'shop_code_field_name': имя поля, где искать код магазина,
        'receipt_code_field_name': имя поля, где искать receipt code (uuid),
        'dttm_field_name': имя поля, где искать дату и время события,
        'data_type': тип данных
}
'''


@app.task
def aggregate_timeserie_value():
    """
    Потенциально для любого вида значений, которые нужно агрегировать в timeserie
    конкретно сейчас для агрегации чеков

    Исходные данные хранятся в виде json в базе данных. как именно агреггировать network.settings_values['receive_data_info']
    представлен в виде списка, каждый элемент состоит из:

    :return:
    """

    dttm_now = datetime.now()

    for network in Network.objects.all():
        network.settings_values = json.loads(network.settings_values)
        receive_data_info = network.settings_values.get('receive_data_info', '')

        if receive_data_info:
            for timeserie in receive_data_info:
                grouping_period = timeserie.get('grouping_period', 'h1')
                update_gap = timeserie.get('update_gap', 3)
                for aggregate in timeserie['aggregate']:
                    timeserie_action = aggregate.get('timeserie_action', 'sum')
                    dttm_for_update = (datetime.now() - timedelta(days=update_gap)).replace(hour=0, minute=0, second=0)

                    # check all needed
                    if not (aggregate.get('timeserie_code') and aggregate.get('timeserie_value')):
                        raise Exception(f"no needed values in timeserie: {timeserie}. Network: {network}")

                    print(network, aggregate['timeserie_code'])
                    operation_type_name = OperationTypeName.objects.get(
                        network=network,
                        code=aggregate['timeserie_code'],
                    )

                    # по выборке всех типов очень много может быть, поэтому цикл по магазинам:
                    operations_type = OperationType.objects.filter(
                        shop__network=network,
                        operation_type_name=operation_type_name,
                    ).exclude(
                        dttm_deleted__lte=dttm_now,
                        shop__dttm_deleted__lte=dttm_now,
                    ).select_related('shop')

                    for operation_type in operations_type:
                        items_list = []
                        items = Receipt.objects.filter(shop=operation_type.shop, dttm__gte=dttm_for_update)
                        for item in items:
                            item.info = json.loads(item.info)
                            items_list.append({
                                'dttm': item.dttm,
                                'value': float(item.info.get(aggregate['timeserie_value'], 0))  # fixme: то ли ошибку лучше кидать, то ли пропускать (0 ставить)
                            })

                        item_df = pd.DataFrame(items_list, columns=['dttm', 'value'])
                        dates = pd.date_range(dttm_for_update.date(), dttm_now.date())  # item_df.dttm.dt.date.unique()

                        if grouping_period == 'h1':
                            # todo: вообще в item_df могут быть значения за какие-то периоды, но не за все. Когда нет, то по хорошему
                            # надо ставить 0. Ноооо, скорей всего в этом случае (когда событий мало) нулевые периоды плохо будут
                            # влиять на модель прогноза (если нет события, то риск ошибиться большой).

                            item_df['dttm'] = item_df['dttm'].apply(lambda x: x.replace(minute=0, second=0, microsecond=0))
                        elif grouping_period == 'd1':
                            item_df['dttm'] = item_df['dttm'].apply(lambda x: x.replace(hour=0, minute=0, second=0, microsecond=0))
                            item_df = pd.merge(
                                pd.DataFrame(dates, columns=['dttm']),
                                item_df,
                                on='dttm',
                                how='left',
                            )
                            item_df = item_df.fillna(0)  # пропущенные дни вставляем (в какие то дни что то могут не делать)

                        else:
                            # todo: добавить варианты, когда группируем не по часам.
                            raise NotImplementedError(f'grouping {grouping_period}, timeserie {timeserie}, network {network}')

                        periods_data = item_df.groupby('dttm')['value']
                        if timeserie_action == 'sum':
                            periods_data = periods_data.sum()
                        elif timeserie_action == 'count':
                            periods_data = periods_data.count()
                        else:
                            raise NotImplementedError(f'timeserie_action {timeserie_action}, timeserie {timeserie}, network {network}')

                        periods_data = periods_data.reset_index()
                        PeriodClients.objects.filter(
                            operation_type=operation_type,
                            dttm_forecast__date__in=dates,
                            type=PeriodClients.FACT_TYPE,
                        ).delete()

                        PeriodClients.objects.bulk_create([
                            PeriodClients(
                                operation_type=operation_type,
                                dttm_forecast=period['dttm'],
                                value=period['value'],
                                type=PeriodClients.FACT_TYPE,
                            ) for _, period in periods_data.iterrows()
                        ])


@app.task
def clean_timeserie_actions():
    dttm_now = datetime.now()

    for network in Network.objects.all():
        network.settings_values = json.loads(network.settings_values)
        receive_data_info = network.settings_values.get('receive_data_info', '')

        if receive_data_info:
            for timeserie in receive_data_info:
                delete_gap = timeserie.get('delete_gap', 31)
                dttm_for_delete = (datetime.now() - timedelta(days=delete_gap)).replace(hour=0, minute=0, second=0)

                for aggregate in timeserie['aggregate']:
                    print(network, aggregate['timeserie_code'])
                    operation_type_name = OperationTypeName.objects.get(
                        network=network,
                        code=aggregate['timeserie_code'],
                    )

                    operations_type = OperationType.objects.filter(
                        shop__network=network,
                        operation_type_name=operation_type_name,
                    ).exclude(
                        dttm_deleted__lte=dttm_now,
                        shop__dttm_deleted__lte=dttm_now,
                    ).select_related('shop')
                    for operation_type in operations_type:
                        Receipt.objects.filter(shop=operation_type.shop, dttm__lt=dttm_for_delete).delete()

@app.task
def send_urv_stat():
    if not URV_STAT_EMAILS:
        return
    dt = date.today() - timedelta(days=1)
    title = f'URV_{dt}.xlsx'

    for network_code, emails in URV_STAT_EMAILS.items():
        create_urv(dt, dt, title=title, shop_level=URV_STAT_SHOP_LEVEL, network_id=Network.objects.get(code=network_code).id)
        msg = EmailMultiAlternatives(
            subject=f'Отчёт УРВ {dt}',
            body=f'Отчёт УРВ {dt}',
            from_email=EMAIL_HOST_USER,
            to=emails,
        )
        msg.attach_file(title)
        os.remove(title)
        result = msg.send()

    return


@app.task
def send_urv_stat_today():
    if not URV_STAT_EMAILS:
        return
    dt = date.today()
    title = f'URV_today_{dt}.xlsx'

    for network_code, emails in URV_STAT_EMAILS.items():
        create_urv(dt, dt, title=title, shop_level=URV_STAT_SHOP_LEVEL, comming_only=True, network_id=Network.objects.get(code=network_code).id)
        msg = EmailMultiAlternatives(
            subject=f'Отчёт УРВ {dt}',
            body=f'Отчёт УРВ {dt}',
            from_email=EMAIL_HOST_USER,
            to=emails,
        )      
        msg.attach_file(title)
        os.remove(title)    
        result = msg.send()

    return

@app.task
def create_mda_user_to_shop_relation(username, shop_code):
    logger = logging.getLogger('django.request')
    resp = requests.post(
        url=settings.MDA_PUBLIC_API_HOST + '/api/public/v1/mindandmachine/userToShop/',
        json={'login': username, 'sap': shop_code},
        headers={'x-public-token': settings.MDA_PUBLIC_API_AUTH_TOKEN},
        timeout=(3, 5),
    )
    try:
        resp.raise_for_status()
    except requests.RequestException:
        logger.exception(f'text:{resp.text}, headers: {resp.headers}')
