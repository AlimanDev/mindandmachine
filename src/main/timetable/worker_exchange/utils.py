from src.db.models import WorkerDay, WorkerDayCashboxDetails, CashboxType, WorkerCashboxInfo, WorkerConstraint
from django.db.models import Q

import datetime as datetime_module
from datetime import timedelta, time, datetime

from ..cashier_demand.utils import count_diff

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

    ct_user_dict = {}
    for ct_type_id in ct_ids:
        filtered_against_ct_type = worker_day_cashbox_details.filter(cashbox_type_id=ct_type_id)
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


def is_consistent_with_user_constraints(dttm, users):
    """

    :param dttm:
    :param users: list of users objs
    :return: list of users whos constraints dont contradict dttm
    """
    weekday = dttm.weekday()
    return_list = []
    for user in users:
        if not WorkerConstraint.objects.filter(worker=user, weekday=weekday, tm=dttm.time()):
            return_list.append(user)

    return return_list


def from_other_spec(shop_id, dttm_exchange, ct_type, predict_demand, mean_bills_per_step, cashbox_types):
    """

    :param shop_id:
    :param dttm_exchange:
    :param ct_type:
    :param predict_demand:
    :param mean_bills_per_step:
    :param cashbox_types:
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id] }
    """
    #presets
    demand_ind = 0
    hard_cts_in_shop = []
    for x in CashboxType.objects.filter(shop_id=shop_id, do_forecast=CashboxType.FORECAST_HARD).values('id').order_by('id'):
        hard_cts_in_shop.append(x['id'])
    users_who_can_work_on_ct = get_users_who_can_work_on_ct_type(ct_type)

    #tm settings
    tm_interval = 60  # minutes
    standard_tm_interval = 30  # minutes
    dttm_sections = []

    tm = dttm_exchange - timedelta(minutes=tm_interval / 2)
    while tm <= dttm_exchange + timedelta(minutes=tm_interval / 2):
        dttm_sections.append(tm)
        tm += timedelta(minutes=standard_tm_interval)

    users_for_exchange = {}
    to_consider = {}  # рассматривать ли вообще тип касс или нет
    for hard_ct in hard_cts_in_shop:
        if hard_ct == ct_type:
            to_consider[hard_ct] = False
        else:
            to_consider[hard_ct] = True

    for dttm in dttm_sections:
        predict_diff_dict, demand_ind = count_diff(dttm, predict_demand, demand_ind, mean_bills_per_step, cashbox_types)
        users_working_on_hard_cts_at_dttm = get_cashiers_working_at_time_on(dttm, hard_cts_in_shop)  # dict {ct_id: users}
        for cashbox_type in predict_diff_dict.keys():
            number_of_workers = len(users_working_on_hard_cts_at_dttm[cashbox_type])
            if int(predict_diff_dict[cashbox_type]) + 1 < number_of_workers != 1 and to_consider[cashbox_type]:
                for user in users_working_on_hard_cts_at_dttm[cashbox_type]:
                    if user in users_who_can_work_on_ct:
                        if user not in users_for_exchange.keys():
                            users_for_exchange[user] = []
                            users_for_exchange[user].append(get_key_by_value(CHANGE_TYPE_CHOICES, 'FROM OTHER SPEC'))
                            users_for_exchange[user].append(cashbox_type)
                        else:
                            if cashbox_type not in users_for_exchange[user]:
                                users_for_exchange[user].append(cashbox_type)

            else:
                to_consider[cashbox_type] = False

    return users_for_exchange


def day_switch(shop_id, dttm_exchange, ct_type, predict_demand, mean_bills_per_step, cashbox_types):
    """

    :param shop_id:
    :param dttm_exchange:
    :param ct_type:
    :param predict_demand:
    :param mean_bills_per_step:
    :param cashbox_types:
    :return: dict = { user : [CHANGE_TYPE, from which cashbox id] }
    """
    #presets
    demand_ind = 0
    hard_cts_in_shop = []
    for x in CashboxType.objects.filter(shop_id=shop_id, do_forecast=CashboxType.FORECAST_HARD).values('id').order_by('id'):
        hard_cts_in_shop.append(x['id'])
    users_who_can_work_on_ct = get_users_who_can_work_on_ct_type(ct_type)

    #tm settings
    day_begin_dttm = datetime.combine(dttm_exchange.date(), time(6, 30))
    day_end_dttm = datetime.combine(dttm_exchange.date() + timedelta(days=1), time(2, 0))
    standard_tm_interval = 30  # minutes
    amount_of_hours_to_count_transplant = 5  # hours

    users_for_exchange = {}
    to_collect = {}  # { cashbox type: [True/False, amount of intervals] }
    # transplant_interval_dict = {}  # { cashbox type : {(dttm1, dttm2) : [users]} }
    # interval_dict = {}  # {(dttm1, dttm2) : users}
    # to_consider = {}  # рассматривать ли вообще тип касс или нет
    # for hard_ct in hard_cts_in_shop:
    #     if hard_ct == ct_type:
    #         to_consider[hard_ct] = False
    #     else:
    #         to_consider[hard_ct] = True

    dttm = day_begin_dttm
    # interval = (dttm, None)
    # interval_dict[interval] = []
    while dttm <= day_end_dttm:
        predict_diff_dict, demand_ind = count_diff(dttm, predict_demand, demand_ind, mean_bills_per_step, cashbox_types)
        users_working_on_hard_cts_at_dttm = get_cashiers_working_at_time_on(dttm, hard_cts_in_shop)  # dict {ct_id: users}
        # print(interval)
        for cashbox_type in predict_diff_dict.keys():
            if cashbox_type not in to_collect.keys():
                to_collect[cashbox_type] = [False, 0]
            # if cashbox_type not in transplant_interval_dict.keys():
            #     transplant_interval_dict[cashbox_type] = interval_dict
            number_of_workers = len(users_working_on_hard_cts_at_dttm[cashbox_type])
            # print('ct type : ', cashbox_type, '; dttm : ', dttm, '; interval : ', interval, '; transplant dict : ', transplant_interval_dict[cashbox_type], '; predict : ', int(predict_diff_dict[cashbox_type]) + 1, '; workers : ', number_of_workers)
            if int(predict_diff_dict[cashbox_type]) + 1 < number_of_workers != 1:
                to_collect[cashbox_type] = [True, to_collect[cashbox_type][1] + 1]
                # old_interval = interval
                # new_interval = update_tuple_value(interval, 1, dttm)
                # print(new_interval, old_interval)
                # print(interval)
                # print(interval_dict[interval])
                # if interval_dict[interval]:
                #     interval_dict[new_interval] = interval_dict[interval]
                # else:
                #     interval_dict[new_interval] = []
                # del interval_dict[interval]
                for user in users_working_on_hard_cts_at_dttm[cashbox_type]:
                    if user in users_who_can_work_on_ct:
                        pass
                        # if interval not in interval_dict.keys():
                        #     interval_dict[interval] = [user]
                        # else:
                        #     interval_dict[interval].append(user)
                        # if user not in users_for_exchange.keys():
                        #     users_for_exchange[user] = []
                        #     users_for_exchange[user].append(get_key_by_value(CHANGE_TYPE_CHOICES, 'FROM OTHER SPEC'))
                        #     users_for_exchange[user].append(cashbox_type)
                        # else:
                        #     if cashbox_type not in users_for_exchange[user]:
                        #         users_for_exchange[user].append(cashbox_type)

            else:
                amount_of_intervals = to_collect[cashbox_type][1]
                to_collect[cashbox_type] = [False, 0]
                # if not interval[1] or int((interval[1] - interval[0]).seconds/3600) < amount_of_hours_to_count_transplant:
                #     interval = (dttm, None)
                # to_consider[cashbox_type] = False
        dttm += timedelta(minutes=standard_tm_interval)

    return users_for_exchange
