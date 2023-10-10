import json
import logging
import os
import shutil
from datetime import date, timedelta, datetime

import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils.timezone import now
from requests.auth import HTTPBasicAuth

from src.apps.base.models import (
    Network,
    Shop,
    User,
    Employment,
)
from src.adapters.celery.celery import app
from src.apps.recognition.models import TickPhoto
from src.common.models_converter import Converter
from src.conf.djconfig import DEFAULT_FROM_EMAIL, URV_DELETE_BIOMETRICS_DAYS_AFTER_FIRED, COMPANY_NAME
from src.apps.events.signals import event_signal
from src.apps.recognition.events import EMPLOYEE_NOT_CHECKED_IN, EMPLOYEE_NOT_CHECKED_OUT
from src.apps.recognition.utils import get_worker_days_with_no_ticks
from src.apps.timetable.models import (
    WorkType,
    WorkerDayCashboxDetails,
    EmploymentWorkType,
)
from src.apps.timetable.worker_day.stat import WorkersStatsGetter


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


@app.task(time_limit=settings.TIME_LIMITS['send_notify_email'])
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
        from_email=DEFAULT_FROM_EMAIL,
        to=user_emails,
        headers={'X-Campaign-Id': COMPANY_NAME}
    )
    if file:
        msg.attach_file(file)

    if html_content:
        msg.attach_alternative(html_content, "text/html")
    result = msg.send()
    return 'Отправлено {} сообщений из {}'.format(result, len(send2user_ids))


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
    not_coming_workers_in_shops, not_leaving_workers_in_shops = get_worker_days_with_no_ticks(dttm)
    for shop_coming in not_coming_workers_in_shops:
        event_signal.send(
            sender=None,
            network_id=shop_coming.get('network_id'),
            event_code=EMPLOYEE_NOT_CHECKED_IN,
            user_author_id=None,
            shop_id=shop_coming.get('shop_id'),
            context=shop_coming,
        )

    for shop_leaving in not_leaving_workers_in_shops:
        event_signal.send(
            sender=None,
            network_id=shop_leaving.get('network_id'),
            event_code=EMPLOYEE_NOT_CHECKED_OUT,
            user_author_id=None,
            shop_id=shop_leaving.get('network_id'),
            context=shop_leaving,
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

    if isinstance(json_data, str):
        json_data = json.loads(json_data)

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
            json=mis_data,
            auth=HTTPBasicAuth(settings.MIS_USERNAME.encode('utf-8'), settings.MIS_PASSWORD.encode('utf-8')),
            timeout=settings.REQUESTS_TIMEOUTS['send_doctors_schedule_to_mis']
        )
        try:
            resp.raise_for_status()
        except requests.RequestException:
            logger.exception(f'text:{resp.text}, wd_data: {wd_data}', )


@app.task
def auto_delete_biometrics():
    from django.db.models import Exists, OuterRef, Subquery
    from src.adapters.tevian.recognition import Recognition
    from src.apps.recognition.models import UserConnecter
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


@app.task
def auto_hard_delete_tick_photos():
    date_to_delete_before = date.today() - relativedelta(months=2)

    TickPhoto.objects.filter(dttm__lte=date_to_delete_before).delete()

    user_photo_path = os.path.join(settings.MEDIA_ROOT, 'user_photo/')

    for folder_name in os.listdir(user_photo_path):
        folder_path = os.path.join(user_photo_path, folder_name)
        try:
            if os.path.isdir(folder_path) and Converter.parse_date(folder_name) < date_to_delete_before:
                shutil.rmtree(folder_path)
        except ValueError:
            pass



@app.task
def set_prod_cal_cache(dt_from):
    if isinstance(dt_from, str):
        dt_from = datetime.strptime(dt_from, settings.QOS_DATETIME_FORMAT).date()
    dt_from = dt_from.replace(day=1)
    dt_to = dt_from + relativedelta(day=31)

    for network in Network.objects.all():
        active_employees = Employment.objects.get_active(
            network_id=network.id,
            dt_from=dt_from, 
            dt_to=dt_to,
        ).values_list('employee_id', flat=True)
        ws_getter = WorkersStatsGetter(dt_from, dt_to, employee_id__in=active_employees, network=network)
        ws_getter._get_prod_cal_cached()


@app.task
def set_prod_cal_cache_cur_and_next_month():
    dt = date.today()
    set_prod_cal_cache.delay(dt)
    set_prod_cal_cache.delay(dt + relativedelta(months=1))
