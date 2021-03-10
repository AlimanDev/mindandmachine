import json
import logging
import os
import time as time_in_secs
from datetime import date, timedelta, datetime
from src.util.models_converter import Converter
import pandas as pd
import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.db import transaction
from django.utils.timezone import now
from src.forecast.load_template.utils import prepare_load_template_request, apply_load_template

from django_celery_beat.models import CrontabSchedule

from src.main.upload.utils import upload_demand_util, upload_employees_util, upload_vacation_util, sftp_download

from src.base.message import Message
from src.base.models import (
    Shop,
    User,
    Notification,
    Subscribe,
    Event,
    Network,
    Employment,
)
from src.celery.celery import app
from src.conf.djconfig import EMAIL_HOST_USER, TIMETABLE_IP, QOS_DATETIME_FORMAT
from src.events.signals import event_signal
from src.forecast.models import (
    OperationTemplate,
    LoadTemplate,
    PeriodClients,
    Receipt,
    OperationType,
    OperationTypeName
)
from src.main.demand.utils import create_predbills_request_function
from src.main.operation_template.utils import build_period_clients
from django.core.serializers.json import DjangoJSONEncoder
from src.timetable.models import (
    WorkType,
    WorkerDayCashboxDetails,
    EmploymentWorkType,
    ShopMonthStat,
    ExchangeSettings,
    WorkerDay,
)
from src.timetable.utils import CleanWdaysHelper
from src.timetable.vacancy.utils import (
    create_vacancies_and_notify,
    cancel_vacancies,
    workers_exchange,
)
from src.timetable.work_type.utils import get_efficiency as get_shop_stats
from src.base.models import ShopSchedule

from src.notifications.models import EventEmailNotification
from src.notifications.tasks import send_event_email_notifications

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


# @app.task
# def calculate_shops_load(lang, load_template_id, dt_from, dt_to, shop_id=None):
#     load_template = LoadTemplate.objects.get(pk=load_template_id)
#     root_shop = Shop.objects.filter(level=0).first()
#     shops = [load_template.shops.get(pk=shop_id)] if shop_id else load_template.shops.all()
#     for shop in shops:
#         res = calculate_shop_load(shop, load_template, dt_from, dt_to, lang=lang)
#         if res['error']:
#             event = Event.objects.create(
#                 type="load_template_err",
#                 params={
#                     'shop': shop,
#                     'message': Message(lang=lang).get_message(res['code'], params=res.get('params', {})),
#                 },
#                 dttm_valid_to=datetime.now() + timedelta(days=2),
#                 shop=root_shop,
#             )
#             create_notifications_for_event(event.id)
@app.task
def calculate_shops_load(load_template_id, dt_from, dt_to, shop_id=None):
    if type(dt_from) == str:
        dt_from = datetime.strptime(dt_from, QOS_DATETIME_FORMAT).date()
    if type(dt_to) == str:
        dt_to = datetime.strptime(dt_to, QOS_DATETIME_FORMAT).date()
    load_template = LoadTemplate.objects.get(pk=load_template_id)
    shops = [load_template.shops.get(pk=shop_id)] if shop_id else load_template.shops.all()
    for shop in shops:
        data = prepare_load_template_request(load_template_id, shop.id, dt_from, dt_to)
        if not (data is None):
            data = json.dumps(data, cls=DjangoJSONEncoder)
            response = requests.post(f'http://{TIMETABLE_IP}/calculate_shop_load/', data=data)



@app.task
def apply_load_template_to_shops(load_template_id, dt_from, shop_id=None):
    if type(dt_from) == str:
        dt_from = datetime.strptime(dt_from, QOS_DATETIME_FORMAT).date()
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


@app.task
def calculate_shop_load_at_night():
    if not settings.CALCULATE_LOAD_TEMPLATE:
        return
    templates = LoadTemplate.objects.filter(
        shops__isnull=False,
    ).distinct('id')
    dt_now = date.today()
    dt_to = (dt_now + relativedelta(months=2)).replace(day=1) - timedelta(days=1)
    for template in templates:
        calculate_shops_load(template.id, dt_now, dt_to)

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
                'timeserie_filters': словарь, например: {"ВидОперации": "Продажа"}
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
                    aggr_filters = aggregate.get('timeserie_filters')
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

                            # Пропускаем записи, которые не удовл. значениям в фильтре
                            if aggr_filters and not all(item.info.get(k) == v for k, v in aggr_filters.items()):
                                continue
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
def create_mda_user_to_shop_relation(username, shop_code, debug_info=None):
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
        logger.exception(f'text:{resp.text}, headers: {resp.headers}, debug_info: {debug_info}')


@app.task
def sync_mda_user_to_shop_relation(dt=None, delay_sec=0.01):
    dt = dt or now().today()
    wdays = WorkerDay.objects.filter(
        Q(is_vacancy=True) | Q(type=WorkerDay.TYPE_QUALIFICATION),
        is_fact=False, is_approved=True,
        shop__isnull=False, worker__isnull=False,
        dt=dt,
    ).values('worker__username', 'shop__code').distinct()
    for wd in wdays:
        create_mda_user_to_shop_relation(username=wd['worker__username'], shop_code=wd['shop__code'])
        if delay_sec:
            time_in_secs.sleep(delay_sec)


@app.task
def clean_wdays(filter_kwargs: dict = None, exclude_kwargs: dict = None, only_logging=True, clean_plan_empl=False):
    clean_wdays_helper = CleanWdaysHelper(
        filter_kwargs=filter_kwargs,
        exclude_kwargs=exclude_kwargs,
        only_logging=only_logging,
        clean_plan_empl=clean_plan_empl,
    )
    clean_wdays_helper.run()


@app.task
def delete_inactive_employment_groups():
    dt_now = date.today()
    Employment.objects.filter(
        dt_to_function_group__lt=dt_now,
    ).update(
        function_group=None,
        dt_to_function_group=None,
    )


@app.task
def fill_shop_schedule(shop_id, dt_from, periods=90):
    """
    Заполнение ShopSchedule стандартным расписанием на опред. период
    :param shop_id: id магазина
    :param dt_from: дата от (включительно)
    :param periods: на сколько дней вперед заполнить расписания от dt_from
    :return:
    """
    if isinstance(dt_from, str):
        dt_from = Converter.parse_date(dt_from)

    shop = Shop.objects.get(id=shop_id)

    existing_shop_schedule_dict = {
        ss.dt: ss for ss in
        ShopSchedule.objects.filter(
            shop_id=shop_id,
            dt__gte=dt_from,
            dt__lte=dt_from + timedelta(days=periods),
        )
    }
    skipped = 0
    to_create = []
    to_update = []
    for dt in pd.date_range(dt_from, periods=periods, normalize=True):
        dt = dt.date()
        existing_shop_schedule = existing_shop_schedule_dict.get(dt)

        if not existing_shop_schedule:
            to_create.append(dt)
            continue

        if existing_shop_schedule.modified_by_id is not None:
            skipped += 1
            continue

        standard_schedule = shop.get_standard_schedule(dt)

        if standard_schedule is None:  # выходной по стандартному расписанию
            if existing_shop_schedule.type != ShopSchedule.HOLIDAY_TYPE \
                    or existing_shop_schedule.opens is not None or existing_shop_schedule.closes is not None:
                to_update.append((dt, (ShopSchedule.HOLIDAY_TYPE, None, None)))
                continue
        else:
            if standard_schedule['tm_open'] != existing_shop_schedule.opens \
                    or standard_schedule['tm_close'] != existing_shop_schedule.closes:
                to_update.append(
                    (dt, (ShopSchedule.WORKDAY_TYPE, standard_schedule['tm_open'], standard_schedule['tm_close']))
                )
                continue

        skipped += 1

    if to_create:
        shop_schedules_to_create = []
        for dt in to_create:
            standard_schedule = shop.get_standard_schedule(dt=dt)
            shop_schedules_to_create.append(
                ShopSchedule(
                    shop_id=shop_id,
                    dt=dt,
                    opens=standard_schedule['tm_open'] if standard_schedule else None,
                    closes=standard_schedule['tm_close'] if standard_schedule else None,
                    type=ShopSchedule.WORKDAY_TYPE if standard_schedule else ShopSchedule.HOLIDAY_TYPE,
                )
            )
        ShopSchedule.objects.bulk_create(shop_schedules_to_create)

    if to_update:
        for dt, (schedule_type, opens, closes) in to_update:
            ShopSchedule.objects.update_or_create(
                shop_id=shop_id,
                dt=dt,
                defaults={
                    'type': schedule_type,
                    'opens': opens,
                    'closes': closes,
                },
            )

    return {'created': len(to_create), 'updated': len(to_update), 'skipped': skipped}


@app.task
def fill_active_shops_schedule():
    res = {}
    dttm_now = datetime.now()
    dt_now = dttm_now.date()
    active_shops_qs = Shop.objects.filter(
        Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gt=dttm_now),
        Q(dt_closed__isnull=True) | Q(dt_closed__gt=dt_now),
    )
    for shop_id in active_shops_qs.values_list('id', flat=True):
        res[shop_id] = fill_shop_schedule(shop_id, dt_now)

    return res


@app.task
def recalc_wdays(**kwargs):
    wdays_qs = WorkerDay.objects.filter(type__in=WorkerDay.TYPES_WITH_TM_RANGE, **kwargs)
    for wd_id in wdays_qs.values_list('id', flat=True):
        with transaction.atomic():
            wd_obj = WorkerDay.objects.filter(id=wd_id).select_for_update().first()
            if wd_obj:
                wd_obj.save()


@app.task
def trigger_event(**kwargs):
    event_signal.send(sender=None, **kwargs)


@app.task
def cron_event():
    dttm = datetime.now()
    crons = CrontabSchedule.objects.all()
    posible_crons = []
    for cron in crons:
        schedule = cron.schedule
        if (
            dttm.minute in schedule.minute and
            dttm.hour in schedule.hour and
            dttm.weekday() in schedule.day_of_week and
            dttm.day in schedule.day_of_month and
            dttm.month in schedule.month_of_year
        ):
            posible_crons.append(cron)
    events = EventEmailNotification.objects.filter(
        cron__in=posible_crons,
    )
    for event_email_notification in events:
        send_event_email_notifications.delay(
            event_email_notification_id=event_email_notification.id,
            user_author_id=None,
            context={},
        )


@app.task
def send_doctors_schedule_to_mis(json_data):
    """
    Таск для отправки расписания по врачам в МИС
    :param json_data: json строка
    Пример данных:
    [
        {
            "dt": "2021-03-09",
            "worker__username": "user2",
            "shop__code": "code-237",
            "dttm_work_start": "2021-03-09T10:00:00",
            "dttm_work_end": "2021-03-09T20:00:00",
            "action": "create"
        },
        {
            "dt": "2021-03-10",
            "worker__username": "user2",
            "shop__code": "code-237",
            "dttm_work_start": "2021-03-10T08:00:00",
            "dttm_work_end": "2021-03-10T21:00:00",
            "action": "update"
        },
        {
            "dt": "2021-03-11",
            "worker__username": "user2",
            "shop__code": "code-237",
            "dttm_work_start": null,
            "dttm_work_end": null,
            "action": "delete"
        }
    ]
    :return:
    """
    print('send_doctors_schedule_to_mis', json_data)
    # TODO: реализовать отправку данных после согласования формата
