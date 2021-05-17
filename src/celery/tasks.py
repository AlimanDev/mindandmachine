import logging
import os
import time as time_in_secs
from datetime import date, timedelta, datetime

import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.utils.timezone import now
from requests.auth import HTTPBasicAuth
from src.main.operation_template.utils import build_period_clients
from src.main.upload.utils import upload_demand_util, upload_employees_util, upload_vacation_util, sftp_download

from src.base.models import (
    Shop,
    User,
    Notification,
    Subscribe,
    Event,
    Employment,
)
from src.celery.celery import app
from src.conf.djconfig import EMAIL_HOST_USER, URV_DELETE_BIOMETRICS_DAYS_AFTER_FIRED
from src.forecast.models import OperationTemplate
from src.events.signals import event_signal
from src.notifications.models import EventEmailNotification
from src.notifications.tasks import send_event_email_notifications
from src.recognition.events import EMPLOYEE_NOT_CHECKED_IN, EMPLOYEE_NOT_CHECKED_OUT
from src.recognition.utils import get_worker_days_with_no_ticks
from src.timetable.models import (
    WorkType,
    WorkerDayCashboxDetails,
    EmploymentWorkType,
)


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
def delete_inactive_employment_groups():
    dt_now = date.today()
    Employment.objects.filter(
        dt_to_function_group__lt=dt_now,
    ).update(
        function_group=None,
        dt_to_function_group=None,
    )


@app.task
def employee_not_checked():
    dttm = datetime.now()
    no_comming, no_leaving = get_worker_days_with_no_ticks(dttm)
    for no_comming_record in no_comming:
        event_signal.send(
            sender=None,
            network_id=no_comming_record.shop.network_id,
            event_code=EMPLOYEE_NOT_CHECKED_IN,
            user_author_id=None,
            shop_id=no_comming_record.shop_id,
            context={
                'user': {
                    'last_name': no_comming_record.worker.last_name,
                    'first_name': no_comming_record.worker.first_name,
                },
                'director': {
                    'email': no_comming_record.shop.director.email if no_comming_record.shop.director else no_comming_record.shop.email,
                    'name': no_comming_record.shop.director.first_name if no_comming_record.shop.director else no_comming_record.shop.name,
                },
                'dttm': no_comming_record.dttm_work_start_plan.strftime('%Y-%m-%dT%H:%M:%S'),
                'type': 'приход',
                'shop_id': no_comming_record.shop_id,
            },
        )

    for no_leaving_record in no_leaving:
        event_signal.send(
            sender=None,
            network_id=no_leaving_record.shop.network_id,
            event_code=EMPLOYEE_NOT_CHECKED_OUT,
            user_author_id=None,
            shop_id=no_leaving_record.shop_id,
            context={
                'user': {
                    'last_name': no_leaving_record.worker.last_name,
                    'first_name': no_leaving_record.worker.first_name,
                },
                'director': {
                    'email': no_leaving_record.shop.director.email if no_leaving_record.shop.director else no_leaving_record.shop.email,
                    'name': no_leaving_record.shop.director.first_name if no_leaving_record.shop.director else no_leaving_record.shop.name,
                },
                'dttm': no_leaving_record.dttm_work_end_plan.strftime('%Y-%m-%dT%H:%M:%S'),
                'type': 'уход',
                'shop_id': no_leaving_record.shop_id,
            },
        )


SET_SCHEDULE_METHODS = {
    'create': 'CreateGrafic',
    'update': 'UpdateGrafic',
    'delete': 'DeleteGrafic',
}


@app.task
def send_doctors_schedule_to_mis(json_data, logger=logging.getLogger('send_doctors_schedule_to_mis')):
    """
    Таск для отправки расписания по врачам в МИС
    :param json_data: json строка
    Пример данных:
    [
        {
            "dt": "2021-03-09",
            "employee__user__username": "user2",
            "shop__code": "code-237",
            "dttm_work_start": "2021-03-09T10:00:00",
            "dttm_work_end": "2021-03-09T20:00:00",
            "action": "create"
        },
        {
            "dt": "2021-03-10",
            "employee__user__username": "user2",
            "shop__code": "code-237",
            "dttm_work_start": "2021-03-10T08:00:00",
            "dttm_work_end": "2021-03-10T21:00:00",
            "action": "update"
        },
        {
            "dt": "2021-03-11",
            "employee__user__username": "user2",
            "shop__code": "code-237",
            "dttm_work_start": "2021-03-11T08:00:00",
            "dttm_work_end": "2021-03-11T12:00:00",
            "action": "delete"
        }
    ]
    :return:
    """
    if settings.MIS_USERNAME is None or settings.MIS_PASSWORD is None:
        raise Exception('no auth settings')

    for wd_data in json_data:
        mis_data = {
            'TabelNumber': wd_data['employee__user__username'],
            'KodSalona': wd_data['shop__code'],
            'DataS': wd_data['dttm_work_start'],
            'DataPo': wd_data['dttm_work_end'],
            'Metod': SET_SCHEDULE_METHODS.get(wd_data['action']),
        }
        resp = requests.post(
            url='https://star.nikamed.ru/mc/hs/Telemed/SetSchedule/',
            data=mis_data,
            auth=HTTPBasicAuth(settings.MIS_USERNAME, settings.MIS_PASSWORD)
        )
        try:
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception(f'text:{resp.text}, wd_data: {wd_data}', )


@app.task
def auto_delete_biometrics():
    from django.db.models import Exists, OuterRef, Subquery
    from src.recognition.api.recognition import Recognition
    from src.recognition.models import UserConnecter
    from requests.exceptions import HTTPError
    dt_now = date.today()
    dt = dt_now - timedelta(days=URV_DELETE_BIOMETRICS_DAYS_AFTER_FIRED)
    users = User.objects.annotate(
        active_employment_exists=Exists(
            Employment.objects.get_active(
                dt_from=dt_now,
                dt_to=dt_now,
                employee__user_id=OuterRef('pk')
            )
        )
    ).filter(
        active_employment_exists=False,
    ).annotate(
        last_dt_fired=Subquery(
            Employment.objects.filter(
                employee__user_id=OuterRef('pk')
            ).order_by('-dt_fired').values('dt_fired')[:1]
        )
    ).filter(
        last_dt_fired__lte=dt,
    )
    r = Recognition()
    deleted_uc = []
    for uc in UserConnecter.objects.filter(user__in=users):
        try:
            r.delete_person(uc.partner_id)
            deleted_uc.append(uc.user_id)
        except HTTPError:
            return
    UserConnecter.objects.filter(user_id__in=deleted_uc).delete()
