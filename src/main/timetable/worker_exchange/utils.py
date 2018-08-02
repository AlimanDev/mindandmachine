from src.db.models import (WorkerDay, WorkerDayCashboxDetails,
                           CashboxType, WorkerCashboxInfo,
                           WorkerConstraint, User)

from django.db.models import Q

import datetime as datetime_module
from datetime import timedelta, time, datetime

from ..cashier_demand.utils import count_diff
from src.main.tablet.utils import time_diff
from enum import Enum


class ChangeType(Enum):
    from_other_spec = 1
    day_switch = 2
    excess_dayoff = 3
    overworking = 4
    from_other_spec_part = 5
    from_evening_line = 6
    dayoff = 7


def get_cashiers_working_at_time_on(dttm, ct_ids):
    """
    :param ct_ids: list of CashboxType ids
    :param dttm: datetime obj
    :return: dict{ct_type_id: list of users, working at ct_type}
    """
    if not isinstance(ct_ids, list):
        ct_ids = [ct_ids]
    worker_day_cashbox_details = WorkerDayCashboxDetails.objects.select_related('worker_day').filter(
        Q(worker_day__tm_work_end__gte=dttm.time()) & Q(worker_day__tm_work_end__lt=datetime_module.time(23, 59)) |
        Q(worker_day__tm_work_end__lt=datetime_module.time(2, 0)),
        worker_day__type=WorkerDay.Type.TYPE_WORKDAY.value,
        worker_day__tm_work_start__lte=dttm.time(),
        worker_day__worker_shop=CashboxType.objects.get(id=ct_ids[0]).shop,
        worker_day__dt=dttm.date(),
    )

    ct_user_dict = {}
    for ct_type_id in ct_ids:
        filtered_against_ct_type = worker_day_cashbox_details.filter(cashbox_type=ct_type_id)
        ct_user_dict[ct_type_id] = []
        for worker_day_cashbox_details_obj in filtered_against_ct_type:
            if worker_day_cashbox_details_obj.worker_day.worker not in ct_user_dict[ct_type_id]:
                ct_user_dict[ct_type_id].append(worker_day_cashbox_details_obj.worker_day.worker)
    return ct_user_dict


def get_users_who_can_work_on_ct_type(ct_id):
    """

    :param ct_id:
    :return: list of users who can work on cashbox type with id=ct_id
    """
    wci = WorkerCashboxInfo.objects.filter(cashbox_type_id=ct_id, is_active=True)
    users = []
    for wci_obj in wci:
        users.append(wci_obj.worker)
    return users


def is_consistent_with_user_constraints(dttm, user):
    """

    :param dttm:
    :param user: user obj
    :return: True if user can work at dttm, else : False
    """
    weekday = dttm.weekday()
    return True if not WorkerConstraint.objects.filter(worker=user, weekday=weekday, tm=dttm.time()) else False


def get_intervals_with_excess(arguments_dict):
    """
    returns intervals with excess of workers for each cashbox type
    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': {cashbox_type_id : cashbox_type obj} }
    :return: { cashbox type: [dttm_start, dttm_end, dttm_start2, dttm_end2, ..] }
    """
    to_collect = {}  # { cashbox type: [amount of intervals] }
    dttm_to_collect = {}

    amount_of_hours_to_count_deficiency = 4
    standard_tm_interval = 30
    demand_ind = 0

    day_begin_dttm = datetime.combine(arguments_dict['dttm_exchange'].date(), time(6, 30))
    day_end_dttm = datetime.combine(arguments_dict['dttm_exchange'].date() + timedelta(days=1), time(2, 0))

    dttm = day_begin_dttm
    while dttm <= day_end_dttm:
        predict_diff_dict, demand_ind = count_diff(dttm, arguments_dict['predict_demand'], demand_ind, arguments_dict['mean_bills_per_step'], arguments_dict['cashbox_types'])
        users_working_on_hard_cts_at_dttm = get_cashiers_working_at_time_on(dttm, list(arguments_dict['cashbox_types'].keys()))  # dict {ct_id: users}
        for cashbox_type in predict_diff_dict.keys():
            if cashbox_type not in to_collect.keys():
                to_collect[cashbox_type] = [0]
            if cashbox_type not in dttm_to_collect.keys():
                dttm_to_collect[cashbox_type] = [None]
            number_of_workers = len(users_working_on_hard_cts_at_dttm[cashbox_type])
            if int(predict_diff_dict[cashbox_type]) + 1 < number_of_workers != 1:
                if to_collect[cashbox_type][-1] == 0:
                    dttm_to_collect[cashbox_type][-1] = dttm
                to_collect[cashbox_type][-1] += 1

            else:
                amount_of_intervals = to_collect[cashbox_type][-1]
                if amount_of_intervals >= amount_of_hours_to_count_deficiency * 2:
                    to_collect[cashbox_type].append(0)
                    dttm_to_collect[cashbox_type].append(dttm)
                    dttm_to_collect[cashbox_type].append(None)
                else:
                    to_collect[cashbox_type][-1] = 0
                    dttm_to_collect[cashbox_type][-1] = None
        dttm += timedelta(minutes=standard_tm_interval)

    return dttm_to_collect


def from_other_spec(arguments_dict):
    """

    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': dict = {cashbox_type_id : cashbox_type obj}
                             'users_who_can_work: list of users who can work on ct_type }
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id] }
    """
    #presets
    demand_ind = 0
    predict_demand = arguments_dict['predict_demand']
    mean_bills_per_step = arguments_dict['mean_bills_per_step']
    cashbox_types = arguments_dict['cashbox_types']
    list_of_cashbox_type = sorted(list(cashbox_types.keys()))
    users_for_exchange = {}

    #tm settings
    tm_interval = 60  # minutes
    standard_tm_interval = 30  # minutes
    dttm_sections = []

    tm = arguments_dict['dttm_exchange'] - timedelta(minutes=tm_interval / 2)
    while tm <= arguments_dict['dttm_exchange'] + timedelta(minutes=tm_interval / 2):
        dttm_sections.append(tm)
        tm += timedelta(minutes=standard_tm_interval)

    to_consider = {}  # рассматривать ли вообще тип касс или нет
    for hard_ct in list_of_cashbox_type:
        if hard_ct == arguments_dict['ct_type']:
            to_consider[hard_ct] = False
        else:
            to_consider[hard_ct] = True

    for dttm in dttm_sections:
        predict_diff_dict, demand_ind = count_diff(dttm, predict_demand, demand_ind, mean_bills_per_step, cashbox_types)
        users_working_on_hard_cts_at_dttm = get_cashiers_working_at_time_on(dttm, list_of_cashbox_type)  # dict {ct_id: users}
        for cashbox_type in predict_diff_dict.keys():
            number_of_workers = len(users_working_on_hard_cts_at_dttm[cashbox_type])
            if int(predict_diff_dict[cashbox_type]) + 1 < number_of_workers != 1 and to_consider[cashbox_type]:
                for user in users_working_on_hard_cts_at_dttm[cashbox_type]:
                    if user in arguments_dict['users_who_can_work']:
                        if user not in users_for_exchange.keys():
                            users_for_exchange[user.id] = {}
                            users_for_exchange[user.id].update({'type': ChangeType.from_other_spec.value})

            else:
                to_consider[cashbox_type] = False

    return users_for_exchange


def day_switch(arguments_dict):
    """

    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': dict = {cashbox_type_id : cashbox_type obj}
                             'users_who_can_work: list of users who can work on ct_type }
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id] }
    """
    #presets
    users_for_exchange = {}
    dttm_exchange = arguments_dict['dttm_exchange']

    #tm settings
    standard_tm_interval = 30  # minutes

    dttm_to_collect = get_intervals_with_excess(arguments_dict)

    for cashbox_type in dttm_to_collect.keys():
        dttm_start = []
        dttm_end = []
        for i in range(len(dttm_to_collect[cashbox_type]) - 1):
            if i % 2 == 0:
                dttm_start.append(dttm_to_collect[cashbox_type][i])
            else:
                dttm_end.append(dttm_to_collect[cashbox_type][i])

        for i in range(len(dttm_start)):
            dttm = dttm_start[i]
            while dttm <= dttm_end[i]:
                users_working_on_hard_cts_at_dttm = get_cashiers_working_at_time_on(dttm, cashbox_type)  # dict {ct_id: users}
                for user in users_working_on_hard_cts_at_dttm[cashbox_type]:
                    if user in arguments_dict['users_who_can_work'] and is_consistent_with_user_constraints(dttm_exchange, user):
                        users_for_exchange[user.id] = {'type': ChangeType.day_switch.value}
                dttm += timedelta(minutes=standard_tm_interval)

    return users_for_exchange


def excess_dayoff(arguments_dict):
    """
    показываем пользователей у которых выходной в последний день из трехдневного периода, в котором есть dttm_exchange,
    которые могут работать в это время и при этом не будут работать 6 дней подряд
    Например: dttm_exchange=15 июня. Пользователь отдыхает 15, 16 и 17. Можно попросить его выйти 15, за место 17.
    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': dict = {cashbox_type_id : cashbox_type obj}
                             'users_who_can_work: list of users who can work on ct_type }
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id=None, from which date] }
    """
    #presets
    dttm_exchange = arguments_dict['dttm_exchange']
    users_for_exchange = {}

    days_list_to_check_for_6_days_constraint = []
    dttm_to_start_check = dttm_exchange - timedelta(days=5)
    while dttm_to_start_check < dttm_exchange:
        days_list_to_check_for_6_days_constraint.append(dttm_to_start_check.date())
        dttm_to_start_check += timedelta(days=1)

    users_with_holiday_on_dttm_exchange = WorkerDay.objects.filter(dt=dttm_exchange.date(), type=WorkerDay.Type.TYPE_HOLIDAY.value, worker_shop=arguments_dict['shop_id'])

    for worker_day_of_user in users_with_holiday_on_dttm_exchange:
        worker = worker_day_of_user.worker
        if WorkerDay.objects.get(worker=worker, dt=(dttm_exchange - timedelta(1)).date()).type == WorkerDay.Type.TYPE_HOLIDAY.value:
            if WorkerDay.objects.get(worker=worker, dt=(dttm_exchange - timedelta(2)).date()).type == WorkerDay.Type.TYPE_HOLIDAY.value:
                if is_consistent_with_user_constraints(dttm_exchange, worker) and worker in arguments_dict['users_who_can_work']:
                    users_for_exchange[worker.id] = {}
                    users_for_exchange[worker.id].update({'type': ChangeType.excess_dayoff.value})
                    continue
            elif WorkerDay.objects.get(worker=worker, dt=(dttm_exchange + timedelta(1)).date()).type == WorkerDay.Type.TYPE_HOLIDAY.value:
                if is_consistent_with_user_constraints(dttm_exchange, worker) and worker in arguments_dict['users_who_can_work']:
                    users_for_exchange[worker.id] = {}
                    users_for_exchange[worker.id].update({'type': ChangeType.excess_dayoff.value})
                    continue
        else:
            if WorkerDay.objects.get(worker=worker, dt=(dttm_exchange + timedelta(1)).date()).type == WorkerDay.Type.TYPE_HOLIDAY.value:
                if WorkerDay.objects.get(worker=worker, dt=(dttm_exchange + timedelta(2)).date()).type == WorkerDay.Type.TYPE_HOLIDAY.value:
                    if len(WorkerDay.objects.filter(worker=worker, dt__in=days_list_to_check_for_6_days_constraint, type=WorkerDay.Type.TYPE_WORKDAY.value)) < 5:
                        if is_consistent_with_user_constraints(dttm_exchange, worker) and worker in arguments_dict['users_who_can_work']:
                            users_for_exchange[worker.id] = {}
                            users_for_exchange[worker.id].update({'type': ChangeType.excess_dayoff.value})
                            continue

    return users_for_exchange


def overworking(arguments_dict):
    """
    подработки
    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': dict = {cashbox_type_id : cashbox_type obj},
                             'users_who_can_work: list of users who can work on ct_type}
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id=None, from which date] }
    """
    # presets
    dttm_exchange = arguments_dict['dttm_exchange']
    shop_id = arguments_dict['shop_id']
    users_for_exchange = {}

    users_not_working_wds = WorkerDay.objects.filter(
        Q(tm_work_start__gt=dttm_exchange) | (Q(tm_work_end__lt=dttm_exchange) &
        Q(tm_work_end__gte=datetime_module.time(2, 0))),
        dt=dttm_exchange.date(),
        worker_shop=shop_id,
        type=WorkerDay.Type.TYPE_WORKDAY.value
        )

    for user_wd in users_not_working_wds:
        dttm_exchange_minus = datetime.combine(dttm_exchange.date(), user_wd.tm_work_start) - timedelta(hours=3)
        dttm_exchange_plus = datetime.combine(dttm_exchange.date(), user_wd.tm_work_end) + timedelta(hours=3)
        worker = user_wd.worker
        if dttm_exchange_minus < dttm_exchange and is_consistent_with_user_constraints(dttm_exchange_minus, worker) or \
            dttm_exchange_plus > dttm_exchange and is_consistent_with_user_constraints(dttm_exchange_plus, worker):
            if worker in arguments_dict['users_who_can_work'] and worker.is_ready_for_overworkings and\
                time_diff(user_wd.tm_work_start, user_wd.tm_work_end)/3600 <= 9:
                users_for_exchange[worker.id] = {}
                users_for_exchange[worker.id].update({'type': ChangeType.overworking.value})

    return users_for_exchange

def dayoff(arguments_dict):
    """
    у кого выходной
    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': dict = {cashbox_type_id : cashbox_type obj},
                             'users_who_can_work: list of users who can work on ct_type}
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id=None, from which date] }
    """
    #presets
    dttm_exchange = arguments_dict['dttm_exchange']
    shop_id = arguments_dict['shop_id']
    users_for_exchange = {}

    dayoff_users_wds = WorkerDay.objects.filter(dt=dttm_exchange.date(), type=WorkerDay.Type.TYPE_HOLIDAY.value,
                                                worker_shop=shop_id)

    for user_wd in dayoff_users_wds:
        worker = user_wd.worker
        if is_consistent_with_user_constraints(dttm_exchange, worker) and worker in arguments_dict['users_who_can_work']:
            users_for_exchange[worker.id] = {}
            users_for_exchange[worker.id].update({'type': ChangeType.dayoff.value})

    return users_for_exchange


