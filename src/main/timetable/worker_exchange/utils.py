"""
Note:
    Во всех функциях, которые ищут сотрудников для замены в качестве аргумента используется

    arguments_dict = {
        | 'shop_id': int,
        | 'dttm_exchange_start(datetime.datetime): дата-время, на которые искать замену,
        | 'dttm_exchange_end(datetime.datetime): дата-время, на которые искать замену,
        | 'work_type'(int): на какую специализацию ищем замену,
        | 'predict_demand'(list): QuerySet PeriodDemand'ов,
        | 'mean_bills_per_step'(dict): по ключу -- id типа кассы, по значению -- средняя скорость,
        | 'work_types_dict'(dict): по ключу -- id типа кассы, по значению -- объект
        | 'users_who_can_work(list): список пользователей, которые могут работать на ct_type
    }

    Если одна из функций падает, рейзим ValueError, во вьюхе это отлавливается, и возвращается в 'info' в какой \
    именно функции произошла ошибка.

    А возвращается:
        {
            user_id: {
                | 'type': ,
                | 'tm_start': ,
                | 'tm_end':
            }, ..
        }
"""

from src.db.models import (
    WorkerDay,
    Event,
    User,
    WorkerDayCashboxDetails,
)

from django.db.models import Q
from django.utils import timezone
from src.util.models_converter import BaseConverter


def search_candidates(wd_details, **kwargs):
    """

    :param wd_details: db.WorkerDayCashboxDetails -- only in python, not real model in db. idea: no model until users selected for sending
    :param kwargs: dict {
        |  'own_shop': Boolean, if True then add: искать из своего магазина/отдела только
        |  'other_shops': Boolean, if True then show: искать из своего магазина/отдела только
        |  'other_supershops': Boolean, if True then show: смотрим другие локации
        |  'outsource': Boolean, if True then show, добавляем аутсорс
    }
    :return:
    """

    # department checks

    depart_filter = Q()
    if kwargs['own_shop']:
        depart_filter |= Q(shop_id=wd_details.work_type.shop_id)

    if kwargs['other_shops']:
        depart_filter |= Q(shop__super_shop_id=wd_details.work_type.shop.super_shop_id)

    if kwargs['other_supershops']:
        depart_filter |= Q(shop__super_shop_id__gte=1)

    # todo: add outsource

    # todo: 1. add time gap for check if different shop
    # todo: 2. add WorkerCashboxInfo check if necessary
    # todo: 3. add Location check
    workers = User.objects.filter(

        Q(workerday__type__in=[
            WorkerDay.Type.TYPE_HOLIDAY.value,
            WorkerDay.Type.TYPE_VACATION.value,
            WorkerDay.Type.TYPE_EMPTY.value,
            WorkerDay.Type.TYPE_DELETED.value,
            WorkerDay.Type.TYPE_HOLIDAY_SPECIAL.value,
        ]) |
        Q(workerday__type=WorkerDay.Type.TYPE_WORKDAY.value, workerday__dttm_work_start__gte=wd_details.dttm_to) |
        Q(workerday__type=WorkerDay.Type.TYPE_WORKDAY.value,workerday__dttm_work_end__lte=wd_details.dttm_from),
        depart_filter,

        dt_fired__isnull=True,
        is_ready_for_overworkings=True,

        workerday__dt=wd_details.dttm_from.date(),
        workerday__child__isnull=True,
    )
    print(workers.query.__str__())
    # import pdb
    # pdb.set_trace()

    return workers


def send_noti2candidates(users, worker_day_detail):
    event = Event.objects.mm_event_create(
        users,
        push_title='Открыта вакансия на {}'.format(BaseConverter.convert_date(worker_day_detail.dttm_from.date())),

        text='',
        department_id=worker_day_detail.work_type.shop_id,
        to_workerday=worker_day_detail,
    )
    return event


def cancel_vacancy(vacancy_id):
    WorkerDayCashboxDetails.objects.filter(id=vacancy_id, is_vacancy=True).update(
        dttm_deleted=timezone.now(),
        status=WorkerDayCashboxDetails.TYPE_VACANCY,
    )


# def confirm_vacancy(vacancy_id, user):
#     """
#
#     :param vacancy_id:
#     :param user:
#     :return:
#     0 -- все ок
#     1 -- нет открытой вакансии
#     2 -- не может подтвердить с учетом графика (пересечение есть)
#     """
#     vacancy = WorkerDayCashboxDetails.objects.filter(
#         id=vacancy_id,
#         is_vacancy=True,
#         dttm_deleted__isnull=True,
#         worker_day__isnull=True,
#     ).last()
#     if vacancy is None:
#         return 1
#
#
#     workerday = WorkerDay.objects.qos_current_version().filter(
#         dt=vacancy.dttm_from.date(),
#         worker=user,
#     ).last()
#
#     # todo: add better time checker if not the same
#     WorkerDayCashboxDetails.objects.filter(
#         worker_day=workerday,
#
#     )

