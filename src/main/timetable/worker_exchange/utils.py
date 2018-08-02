from src.db.models import WorkerDay, WorkerDayCashboxDetails, CashboxType, WorkerCashboxInfo, WorkerConstraint
from django.db.models import Q

import datetime as datetime_module
from datetime import timedelta, time, datetime

from ..cashier_demand.utils import count_diff

FROMOTHERSPEC = 1

CHANGE_TYPE_CHOICES = {
    1: 'FROM OTHER SPEC',
    2: 'DAY SWITCH',
    3: 'EXCESS DAYOFF',
    4: 'OVERWORKINGS',
    5: 'FROM OTHER SPEC, 50%',
    6: 'FROM EVENING IN CASE LESS THAN 5',
    7: 'DAYOFF'
}


def get_key_by_value(dict_, value):
    return list(dict_.keys())[list(dict_.values()).index(value)]


def update_tuple_value(tpl, ind, new_value):
    lst = list(tpl)
    lst[ind] = new_value
    return tuple(lst)


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
    # print(list(worker_day_cashbox_details))
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


def get_intervals_with_deficiency(arguments_dict):
    to_collect = {}  # { cashbox type: [amount of intervals] }
    dttm_to_collect = {}  # { cashbox type: [dttm_start, dttm_end, dttm_start2, dttm_end2, ..] }

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
                             'mean_bills_per_step': list, 'cashbox_types': dict = {cashbox_type_id : cashbox_type obj} }
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id] }
    """
    #presets
    demand_ind = 0
    predict_demand = arguments_dict['predict_demand']
    mean_bills_per_step = arguments_dict['mean_bills_per_step']
    cashbox_types = arguments_dict['cashbox_types']
    list_of_cashbox_type = sorted(list(cashbox_types.keys()))

    #tm settings
    tm_interval = 60  # minutes
    standard_tm_interval = 30  # minutes
    dttm_sections = []

    tm = arguments_dict['dttm_exchange'] - timedelta(minutes=tm_interval / 2)
    while tm <= arguments_dict['dttm_exchange'] + timedelta(minutes=tm_interval / 2):
        dttm_sections.append(tm)
        tm += timedelta(minutes=standard_tm_interval)

    users_for_exchange = {}
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
                            users_for_exchange[user] = []
                            users_for_exchange[user].append(1)
                            users_for_exchange[user].append(cashbox_type)
                        else:
                            if cashbox_type not in users_for_exchange[user]:
                                users_for_exchange[user].append(cashbox_type)

            else:
                to_consider[cashbox_type] = False

    return users_for_exchange


def day_switch(arguments_dict):
    """

    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': dict = {cashbox_type_id : cashbox_type obj} }
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id] }
    """
    #presets
    demand_ind = 0
    predict_demand = arguments_dict['predict_demand']
    mean_bills_per_step = arguments_dict['mean_bills_per_step']
    cashbox_types = arguments_dict['cashbox_types']
    list_of_cashbox_types = sorted(list(cashbox_types.keys()))

    #tm settings
    day_begin_dttm = datetime.combine(arguments_dict['dttm_exchange'].date(), time(6, 30))
    day_end_dttm = datetime.combine(arguments_dict['dttm_exchange'].date() + timedelta(days=1), time(1, 0))
    standard_tm_interval = 30  # minutes
    amount_of_hours_to_count_transplant = 4  # hours

    users_for_exchange = {}
    to_collect = {}  # { cashbox type: [amount of intervals] }
    dttm_to_collect = {}  # { cashbox type: [dttm_start, dttm_end, dttm_start2, dttm_end2, ..] }

    dttm = day_begin_dttm
    while dttm <= day_end_dttm:
        predict_diff_dict, demand_ind = count_diff(dttm, predict_demand, demand_ind, mean_bills_per_step, cashbox_types)
        users_working_on_hard_cts_at_dttm = get_cashiers_working_at_time_on(dttm, list_of_cashbox_types)  # dict {ct_id: users}
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
                if amount_of_intervals >= amount_of_hours_to_count_transplant * 2:
                    to_collect[cashbox_type].append(0)
                    dttm_to_collect[cashbox_type].append(dttm)
                    dttm_to_collect[cashbox_type].append(None)
                else:
                    to_collect[cashbox_type][-1] = 0
                    dttm_to_collect[cashbox_type][-1] = None
        dttm += timedelta(minutes=standard_tm_interval)

    # print(dttm_to_collect)

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
                # print(users_working_on_hard_cts_at_dttm[cashbox_type], cashbox_type)
                # print(users_working_on_hard_cts_at_dttm)
                for user in users_working_on_hard_cts_at_dttm[cashbox_type]:
                    # if cashbox_type == 16:
                    #     print(users_working_on_hard_cts_at_dttm[cashbox_type], dttm)
                    if user in arguments_dict['users_who_can_work'] and is_consistent_with_user_constraints(arguments_dict['dttm_exchange'], user):
                        users_for_exchange[user] = [get_key_by_value(CHANGE_TYPE_CHOICES, 'DAY SWITCH'), cashbox_type]
                        if cashbox_type not in users_for_exchange[user]:
                            users_for_exchange[user].append(cashbox_type)
                dttm += timedelta(minutes=standard_tm_interval)

    return users_for_exchange


def excess_dayoff(arguments_dict):
    """
    показываем пользователей у которых выходной в последний день из трехдневного периода, в котором есть dttm_exchange,
    которые могут работать в это время и при этом не будут работать 6 дней подряд
    Например: dttm_exchange=15 июня. Пользователь отдыхает 15, 16 и 17. Можно попросить его выйти 15, за место 17.
    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': dict = {cashbox_type_id : cashbox_type obj} }
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id=None, from which date] }
    """

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
                    users_for_exchange[worker] = [get_key_by_value(CHANGE_TYPE_CHOICES, 'EXCESS DAYOFF'), None, dttm_exchange.date()]
                    continue
            elif WorkerDay.objects.get(worker=worker, dt=(dttm_exchange + timedelta(1)).date()).type == WorkerDay.Type.TYPE_HOLIDAY.value:
                if is_consistent_with_user_constraints(dttm_exchange, worker) and worker in arguments_dict['users_who_can_work']:
                    users_for_exchange[worker] = [get_key_by_value(CHANGE_TYPE_CHOICES, 'EXCESS DAYOFF'), None, (dttm_exchange+timedelta(1)).date()]
                    continue
        else:
            if WorkerDay.objects.get(worker=worker, dt=(dttm_exchange + timedelta(1)).date()).type == WorkerDay.Type.TYPE_HOLIDAY.value:
                if WorkerDay.objects.get(worker=worker, dt=(dttm_exchange + timedelta(2)).date()).type == WorkerDay.Type.TYPE_HOLIDAY.value:
                    if len(WorkerDay.objects.filter(worker=worker, dt__in=days_list_to_check_for_6_days_constraint, type=WorkerDay.Type.TYPE_WORKDAY.value)) < 5:
                        if is_consistent_with_user_constraints(dttm_exchange, worker) and worker in arguments_dict['users_who_can_work']:
                            users_for_exchange[worker] = [get_key_by_value(CHANGE_TYPE_CHOICES, 'EXCESS DAYOFF'), None, (dttm_exchange+timedelta(2)).date()]
                            continue

    return users_for_exchange
