from src.db.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    CashboxType,
    WorkerCashboxInfo,
    WorkerConstraint,
    User
)

from django.db.models import Q

import datetime as datetime_module
from datetime import timedelta, time, datetime

from ..cashier_demand.utils import count_diff
from src.main.tablet.utils import time_diff
from django.core.exceptions import ObjectDoesNotExist
from enum import Enum
from src.util.models_converter import BaseConverter


class ChangeType(Enum):
    """
    не забудь добавить новую функция в ChangeTypeFunctions в конце файла
    число -- приоритет: чем меньше -- тем важнее
    """
    from_other_spec = 1
    day_switch = 2
    excess_dayoff = 3
    overworking = 4
    from_other_spec_part = 5
    from_evening_line = 6
    dayoff = 7
    sos_group = 8


standard_tm_interval = 30  # minutes


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


def is_consistent_with_user_constraints(user, dttm_start, dttm_end):
    """

    :param user: user obj
    :param dttm_start:
    :param dttm_end:
    :return: True if user can work at [dttm_start, dttm_end] interval, else : False
    """

    dttm = dttm_start
    while dttm <= dttm_end:
        weekday = dttm_start.weekday()
        if WorkerConstraint.objects.filter(worker=user, weekday=weekday, tm=dttm.time()):
            return False
        dttm += timedelta(standard_tm_interval)
    return True


def get_intervals_with_excess(arguments_dict):
    """
    returns intervals with excess of workers for each cashbox type
    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': {cashbox_type_id : [cashbox_type obj]} }
    :return: { cashbox type: [dttm_start, dttm_end, dttm_start2, dttm_end2, ..] }
    """
    to_collect = {}  # { cashbox type: [amount of intervals] }
    dttm_to_collect = {}

    amount_of_hours_to_count_deficiency = 4
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
            if int(predict_diff_dict[cashbox_type]) + 1 < number_of_workers and number_of_workers > 1:
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


def has_deficiency(predict_demand, mean_bills_per_step, cashbox_types, dttm):
    """

    :return: { cashbox type: True/False }
    True -- if there is deficiency behind cashbox type, False -- if other case
    """
    ct_deficieny_dict = {}

    demand_ind = 0
    predict_diff_dict, demand_ind = count_diff(dttm, predict_demand, demand_ind, mean_bills_per_step, cashbox_types)

    users_working_on_hard_cts_at_dttm = get_cashiers_working_at_time_on(dttm, list(cashbox_types.keys()))
    for cashbox_type in predict_diff_dict.keys():
        if cashbox_type not in ct_deficieny_dict.keys():
            ct_deficieny_dict[cashbox_type] = False
        number_of_workers = len(users_working_on_hard_cts_at_dttm[cashbox_type])
        if int(predict_diff_dict[cashbox_type]) > number_of_workers:
            ct_deficieny_dict[cashbox_type] = True
        else:
            ct_deficieny_dict[cashbox_type] = False

    return ct_deficieny_dict


def shift_user_times(dttm_exchange, user):
    threshold_time = datetime_module.time(0, 30)
    tm_start_case_threshold = datetime_module.time(15, 30)

    dttm = dttm_exchange
    while dttm >= dttm_exchange + timedelta(minutes=standard_tm_interval) - timedelta(hours=9):
        user_new_dttm_work_start = dttm_exchange - timedelta(minutes=standard_tm_interval)
        user_new_tm_work_start = user_new_dttm_work_start.time()
        user_old_tm_work_start = WorkerDay.objects.get(dt=dttm_exchange.date(), worker=user).tm_work_start
        user_old_tm_work_end = WorkerDay.objects.get(dt=dttm_exchange.date(), worker=user).tm_work_end

        if user_old_tm_work_end is None:  # for excess days
            user_old_dttm_work_end = dttm_exchange + timedelta(hours=4, minutes=30)
        else:
            user_old_dttm_work_end = datetime.combine(dttm_exchange.date(), user_old_tm_work_end) if user_old_tm_work_end > datetime_module.time(2, 0)\
                else datetime.combine((dttm_exchange + timedelta(days=1)).date(), user_old_tm_work_end)
        if user_old_tm_work_start is None:
            user_old_tm_work_start = (datetime.combine(dttm_exchange.date(), (dttm_exchange - timedelta(hours=4, minutes=30)).time())).time()

        diff = abs(datetime.combine(dttm_exchange.date(), user_new_tm_work_start) - datetime.combine(dttm_exchange.date(),
                                                                                                     user_old_tm_work_start)) \
            if user_old_dttm_work_end.time() > datetime_module.time(2, 0) \
            else abs(datetime.combine(dttm_exchange.date(), user_new_tm_work_start) - datetime.combine(
            (dttm_exchange + timedelta(1)).date(), user_old_tm_work_start))

        user_new_dttm_work_end = user_old_dttm_work_end - timedelta(minutes=int(diff.total_seconds() / 60)) \
            if user_new_tm_work_start < user_old_tm_work_start else user_old_dttm_work_end + timedelta(
            minutes=int(diff.total_seconds() / 60))
        user_new_tm_work_end = user_new_dttm_work_end.time() if user_new_dttm_work_end < datetime.combine(
            (dttm_exchange + timedelta(1)).date(), threshold_time) \
            else threshold_time
        if user_new_tm_work_end == threshold_time:
            user_new_tm_work_start = tm_start_case_threshold
        if is_consistent_with_user_constraints(user, user_new_dttm_work_start, user_new_dttm_work_end):
            return user_new_tm_work_start, user_new_tm_work_end
        dttm -= timedelta(minutes=standard_tm_interval)

    return None, None


def from_other_spec(arguments_dict):
    """
    с другой специлизации + с другой специлизации если там частичные излишки(не менее чем excess_percent * 100%)
    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': {cashbox_type_id : [cashbox_type obj]},
                             'users_who_can_work: list of users who can work on ct_type }
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id] }
    """
    #presets
    demand_ind = 0
    predict_demand = arguments_dict['predict_demand']
    mean_bills_per_step = arguments_dict['mean_bills_per_step']
    cashbox_types = arguments_dict['cashbox_types']
    list_of_cashbox_type = sorted(list(cashbox_types.keys()))
    excess_percent = 0.5
    dttm_exchange = arguments_dict['dttm_exchange']
    users_for_exchange = {}


    #tm settings
    tm_interval = 60  # minutes
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
            if int(predict_diff_dict[cashbox_type]) + 1 < number_of_workers and number_of_workers > 1 and to_consider[cashbox_type]:
                for user in users_working_on_hard_cts_at_dttm[cashbox_type]:
                    if user in arguments_dict['users_who_can_work']:
                        if (number_of_workers - int(predict_diff_dict[cashbox_type])) / number_of_workers > excess_percent:
                            users_for_exchange[user.id] = {}
                            users_for_exchange[user.id].update({
                                'type': ChangeType.from_other_spec_part.value,
                                'tm_start': BaseConverter.convert_time(WorkerDay.objects.get(dt=dttm_exchange.date(), worker=user).tm_work_start),
                                'tm_end': BaseConverter.convert_time(WorkerDay.objects.get(dt=dttm_exchange.date(), worker=user).tm_work_end)
                            })
                        else:
                            users_for_exchange[user.id] = {}
                            users_for_exchange[user.id].update({
                                'type': ChangeType.from_other_spec.value,
                                'tm_start': BaseConverter.convert_time(WorkerDay.objects.get(dt=dttm_exchange.date(), worker=user).tm_work_start),
                                'tm_end': BaseConverter.convert_time(WorkerDay.objects.get(dt=dttm_exchange.date(), worker=user).tm_work_end)
                            })

            else:
                to_consider[cashbox_type] = False

    return users_for_exchange


def day_switch(arguments_dict):
    """

    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': {cashbox_type_id : [cashbox_type obj]} ,
                             'users_who_can_work: list of users who can work on ct_type }
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id] }
    """
    #presets
    users_for_exchange = {}
    dttm_exchange = arguments_dict['dttm_exchange']

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
                    if user in arguments_dict['users_who_can_work']:
                        user_new_tm_work_start, user_new_tm_work_end = shift_user_times(dttm_exchange, user)
                        if user_new_tm_work_start is not None and user_new_tm_work_end is not None:
                            users_for_exchange[user.id] = {}
                            users_for_exchange[user.id].update({
                                'type': ChangeType.day_switch.value,
                                'tm_start': BaseConverter.convert_time(user_new_tm_work_start),
                                'tm_end': BaseConverter.convert_time(user_new_tm_work_end)
                            })
                dttm += timedelta(minutes=standard_tm_interval)

    return users_for_exchange


def excess_dayoff(arguments_dict):
    """
    показываем пользователей у которых выходной в последний день из трехдневного периода, в котором есть dttm_exchange,
    которые могут работать в это время и при этом не будут работать 6 дней подряд
    Например: dttm_exchange=15 июня. Пользователь отдыхает 15, 16 и 17. Можно попросить его выйти 15, за место 17.
    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': {cashbox_type_id : [cashbox_type obj]},
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

    update_dict = {'type': ChangeType.excess_dayoff.value,
                   'tm_start': BaseConverter.convert_time((dttm_exchange - timedelta(hours=4)).time()),
                   'tm_end': BaseConverter.convert_time((dttm_exchange + timedelta(hours=4)).time())
                   }

    users_with_holiday_on_dttm_exchange = WorkerDay.objects.filter(dt=dttm_exchange.date(), type=WorkerDay.Type.TYPE_HOLIDAY.value, worker_shop=arguments_dict['shop_id'])
    try:
        for worker_day_of_user in users_with_holiday_on_dttm_exchange:
            worker = worker_day_of_user.worker
            if WorkerDay.objects.get(worker=worker, dt=(dttm_exchange - timedelta(1)).date()).type == WorkerDay.Type.TYPE_HOLIDAY.value:
                if WorkerDay.objects.get(worker=worker, dt=(dttm_exchange - timedelta(2)).date()).type == WorkerDay.Type.TYPE_HOLIDAY.value:
                    user_new_tm_work_start, user_new_tm_work_end = shift_user_times(dttm_exchange, worker)
                    if user_new_tm_work_start and user_new_tm_work_end and worker in arguments_dict['users_who_can_work']:
                        users_for_exchange[worker.id] = update_dict
                        continue
                elif WorkerDay.objects.get(worker=worker, dt=(dttm_exchange + timedelta(1)).date()).type == WorkerDay.Type.TYPE_HOLIDAY.value:
                    user_new_tm_work_start, user_new_tm_work_end = shift_user_times(dttm_exchange, worker)
                    if user_new_tm_work_start and user_new_tm_work_end and worker in arguments_dict['users_who_can_work']:
                        users_for_exchange[worker.id] = update_dict
                        continue
            else:
                if WorkerDay.objects.get(worker=worker, dt=(dttm_exchange + timedelta(1)).date()).type == WorkerDay.Type.TYPE_HOLIDAY.value:
                    if WorkerDay.objects.get(worker=worker, dt=(dttm_exchange + timedelta(2)).date()).type == WorkerDay.Type.TYPE_HOLIDAY.value:
                        if len(WorkerDay.objects.filter(worker=worker, dt__in=days_list_to_check_for_6_days_constraint, type=WorkerDay.Type.TYPE_WORKDAY.value)) < 5:
                            user_new_tm_work_start, user_new_tm_work_end = shift_user_times(dttm_exchange, worker)
                            if user_new_tm_work_start and user_new_tm_work_end and worker in arguments_dict['users_who_can_work']:
                                users_for_exchange[worker.id] = update_dict
                                continue
    except ObjectDoesNotExist:
        pass

    return users_for_exchange


def overworking(arguments_dict):
    """
    подработки
    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': {cashbox_type_id : [cashbox_type obj]},
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
        user_wd_dttm_work_end = datetime.combine(dttm_exchange.date(), user_wd.tm_work_end) if user_wd.tm_work_end > datetime_module.time(2, 0) else \
            datetime.combine(dttm_exchange.date() + timedelta(days=1), user_wd.tm_work_end)
        user_wd_dttm_word_start = datetime.combine(dttm_exchange.date(), user_wd.tm_work_start)
        dttm_exchange_minus = user_wd_dttm_word_start - timedelta(hours=3)
        dttm_exchange_plus = user_wd_dttm_work_end + timedelta(hours=3)
        worker = user_wd.worker
        if dttm_exchange_minus <= dttm_exchange <= user_wd_dttm_work_end and is_consistent_with_user_constraints(worker, dttm_exchange_minus, dttm_exchange):
            if worker in arguments_dict['users_who_can_work'] and worker.is_ready_for_overworkings and\
                time_diff(user_wd.tm_work_start, user_wd.tm_work_end)/3600 <= 9:
                users_for_exchange[worker.id] = {}
                users_for_exchange[worker.id].update({
                    'type': ChangeType.overworking.value,
                    'tm_start': BaseConverter.convert_time(dttm_exchange_minus.time()),
                    'tm_end': BaseConverter.convert_time(user_wd.tm_work_end)
                })
        elif dttm_exchange_plus >= dttm_exchange >= user_wd_dttm_word_start and is_consistent_with_user_constraints(worker, dttm_exchange, dttm_exchange_plus):
            if worker in arguments_dict['users_who_can_work'] and worker.is_ready_for_overworkings and\
                time_diff(user_wd.tm_work_start, user_wd.tm_work_end)/3600 <= 9 and user_wd_dttm_work_end.time() > datetime_module.time(2, 0):
                users_for_exchange[worker.id] = {}
                users_for_exchange[worker.id].update({
                    'type': ChangeType.overworking.value,
                    'tm_start': BaseConverter.convert_time(user_wd.tm_work_start),
                    'tm_end': BaseConverter.convert_time(dttm_exchange_plus.time())
                })

    return users_for_exchange


def from_evening_line(arguments_dict):
    """
    c вечера (если частичные излишки, или нехватка вечером менее 5 человек(для линии))
    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': {cashbox_type_id : [cashbox_type obj]},
                             'users_who_can_work: list of users who can work on ct_type}
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id=None, from which date] }
    """
    # presets
    dttm_exchange = arguments_dict['dttm_exchange']
    excess_percent = 0.5
    deficit_threshold = 5
    demand_ind = 0
    predict_demand = arguments_dict['predict_demand']
    mean_bills_per_step = arguments_dict['mean_bills_per_step']
    cashbox_types = arguments_dict['cashbox_types']
    list_of_cashbox_type = sorted(list(cashbox_types.keys()))
    users_for_exchange = {}

    #tm settings
    evening_period = [datetime.combine(dttm_exchange.date(), datetime_module.time(17, 0)),
                      datetime.combine(dttm_exchange.date(), datetime_module.time(23, 0))]

    dttm = evening_period[0]
    while dttm <= evening_period[1]:
        predict_diff_dict, demand_ind = count_diff(dttm, predict_demand, demand_ind, mean_bills_per_step, cashbox_types)
        users_working_on_hard_cts_at_dttm = get_cashiers_working_at_time_on(dttm, list_of_cashbox_type)  # dict {ct_id: users}
        for cashbox_type in predict_diff_dict.keys():
            number_of_workers = len(users_working_on_hard_cts_at_dttm[cashbox_type])
            if cashbox_types[cashbox_type][0].is_main_type:
                if 0 < int(predict_diff_dict[cashbox_type]) - number_of_workers < deficit_threshold:
                    for user in users_working_on_hard_cts_at_dttm[cashbox_type]:
                        if user in arguments_dict['users_who_can_work']:
                            user_new_tm_work_start, user_new_tm_work_end = shift_user_times(dttm_exchange, user)
                            if user_new_tm_work_start is not None and user_new_tm_work_end is not None:
                                users_for_exchange[user.id] = {}
                                users_for_exchange[user.id].update({
                                    'type': ChangeType.from_evening_line.value,
                                    'tm_start': BaseConverter.convert_time(user_new_tm_work_start),
                                    'tm_end': BaseConverter.convert_time(user_new_tm_work_end)
                                })
            else:
                if number_of_workers > 1 and (number_of_workers - int(predict_diff_dict[cashbox_type])) / number_of_workers > excess_percent:
                    for user in users_working_on_hard_cts_at_dttm[cashbox_type]:
                        if user in arguments_dict['users_who_can_work']:
                            user_new_tm_work_start, user_new_tm_work_end = shift_user_times(dttm_exchange, user)
                            if user_new_tm_work_start is not None and user_new_tm_work_end is not None:
                                users_for_exchange[user.id] = {}
                                users_for_exchange[user.id].update({
                                    'type': ChangeType.from_evening_line.value,
                                    'tm_start': BaseConverter.convert_time(user_new_tm_work_start),
                                    'tm_end': BaseConverter.convert_time(user_new_tm_work_end)
                                })

        dttm += timedelta(minutes=30)

    return users_for_exchange


def dayoff(arguments_dict):
    """
    у кого выходной
    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': {cashbox_type_id : [cashbox_type obj]},
                             'users_who_can_work: list of users who can work on ct_type}
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id=None, from which date] }
    """
    #presets
    dttm_exchange = arguments_dict['dttm_exchange']
    shop_id = arguments_dict['shop_id']
    users_for_exchange = {}

    dayoff_users_wds = WorkerDay.objects.filter(
        dt=dttm_exchange.date(),
        type=WorkerDay.Type.TYPE_HOLIDAY.value,
        worker_shop=shop_id
    )

    for user_wd in dayoff_users_wds:
        worker = user_wd.worker
        user_new_tm_work_start, user_new_tm_work_end = shift_user_times(dttm_exchange, worker)
        if user_new_tm_work_start and user_new_tm_work_end and worker in arguments_dict['users_who_can_work']:
            users_for_exchange[worker.id] = {
                'type': ChangeType.dayoff.value,
                'tm_start': BaseConverter.convert_time(user_new_tm_work_start),
                'tm_end': BaseConverter.convert_time(user_new_tm_work_end)
            }

    return users_for_exchange


def sos_group(arguments_dict):
    """
    если пришел тип касс -- линия, то берем работников, которые работают в это время на линии, и если у них тип
    SOS, то выбираем их
    :param arguments_dict: { 'shop_id': int, 'dttm_exchange: dttm obj, 'ct_type': int, 'predict_demand': list,
                             'mean_bills_per_step': list, 'cashbox_types': {cashbox_type_id : [cashbox_type obj]},
                             'users_who_can_work: list of users who can work on ct_type}
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id=None, from which date] }
    """
    #presets
    dttm_exchange = arguments_dict['dttm_exchange']
    ct_type = arguments_dict['ct_type']
    users_for_exchange = {}

    line_ct_id = CashboxType.objects.get(is_main_type=True).id

    if ct_type == line_ct_id:
        users_working_on_lines = get_cashiers_working_at_time_on(dttm_exchange, line_ct_id)  # dict {ct_id: users}
        for user in users_working_on_lines[line_ct_id]:
            if user.work_type == User.WorkType.TYPE_SOS.value:
                users_for_exchange[user.id] = {}
                users_for_exchange[user.id].update({
                    'type': ChangeType.sos_group.value,
                    'tm_start': BaseConverter.convert_time(WorkerDay.objects.get(dt=dttm_exchange.date(), worker=user).tm_work_start),
                    'tm_end': BaseConverter.convert_time(WorkerDay.objects.get(dt=dttm_exchange.date(), worker=user).tm_work_end)
                })

    return users_for_exchange


ChangeTypeFunctions = [from_other_spec, day_switch, excess_dayoff, overworking, from_evening_line, dayoff, sos_group]
