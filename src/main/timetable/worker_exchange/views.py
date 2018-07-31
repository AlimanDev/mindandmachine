from datetime import timedelta, time
from datetime import datetime

from src.db.models import (
    PeriodDemand,
)
from .forms import GetWorkersToExchange
from .utils import *
from src.util.utils import api_method, JsonResponse
from django.db.models import Max

from ..cashier_demand.utils import count_diff, check_time_is_between_boarders
from src.util.collection import group_by


@api_method('GET', GetWorkersToExchange)
def get_workers_to_exchange(request, form):
    ct_type = form['specialization']
    dttm_exchange = form['dttm']
    shop_id = form['shop_id'] if form['shop_id'] else request.user.shop_id
    hard_cts_in_shop = []
    for x in CashboxType.objects.filter(shop_id=shop_id, do_forecast=CashboxType.FORECAST_HARD).values('id').order_by('id'):
        hard_cts_in_shop.append(x['id'])

    users_who_can_work_on_ct = get_users_who_can_work_on_ct_type(ct_type)  # list of users
    users_for_exchange = {}  # { key -- user obj : value -- [CHANGE_TYPE, cashbox_type_id] }

    tm_interval = 60  # minutes
    standard_tm_interval = 30  # minutes
    dttm_sections = []
    time_borders = [
        [time(6, 30), time(10, 30), 'morning'],
        [time(18, 30), time(22, 30), 'evening'],
    ]
    intervals_on_day = []

    tm = dttm_exchange - timedelta(minutes=tm_interval / 2)
    while tm <= dttm_exchange + timedelta(minutes=tm_interval / 2):
        dttm_sections.append(tm)
        tm += timedelta(minutes=standard_tm_interval)

    day_begin_dttm = datetime.combine(dttm_exchange.date(), time(6, 30))
    tm = day_begin_dttm
    while tm.time() != time(2, 0):
        intervals_on_day.append(tm)
        tm += timedelta(minutes=standard_tm_interval)

    period_demand = PeriodDemand.objects.filter(
        cashbox_type__shop_id=shop_id,
        dttm_forecast__gte=day_begin_dttm,
        dttm_forecast__lte=intervals_on_day[-1],
        type__in=[
            PeriodDemand.Type.LONG_FORECAST.value,
            PeriodDemand.Type.FACT.value,
        ],
        cashbox_type_id__in=hard_cts_in_shop
    ).order_by(
        'type',
        'dttm_forecast',
        'cashbox_type_id'
    )

    mean_bills_per_step = WorkerCashboxInfo.objects.filter(
        is_active=True,
        cashbox_type_id__in=hard_cts_in_shop
    ).values('cashbox_type_id').annotate(speed_usual=Max('mean_speed'))
    mean_bills_per_step = {m['cashbox_type_id']: m['speed_usual'] for m in mean_bills_per_step}

    edge_ind = 0
    while (edge_ind < len(period_demand)) and (period_demand[edge_ind].type != PeriodDemand.Type.FACT.value):
        edge_ind += 1
    predict_demand = period_demand[:edge_ind]
    demand_ind = 0

    cashbox_types_hard = group_by(CashboxType.objects.filter(shop_id=shop_id, do_forecast=CashboxType.FORECAST_HARD).order_by('id'), group_key=lambda x: x.id)

    for dttm in intervals_on_day:
        predict_diff_dict, demand_ind = count_diff(dttm, predict_demand, demand_ind, mean_bills_per_step, cashbox_types_hard)
        if dttm in dttm_sections or check_time_is_between_boarders(dttm.time(), time_borders):
            for cashbox_type in predict_diff_dict.keys():
                users_working_on_hard_cts_at_dttm = get_cashiers_working_at_time_on(dttm, hard_cts_in_shop)  # dict {ct_id: users}
                number_of_workers = len(users_working_on_hard_cts_at_dttm[cashbox_type])
                # print(dttm, ': ', cashbox_type, ': ', int(predict_diff_dict[cashbox_type]) + 1, len(users_working_on_hard_cts_at_dttm[cashbox_type]))
                if int(predict_diff_dict[cashbox_type]) + 1 < number_of_workers != 1:
                    for user in users_working_on_hard_cts_at_dttm[cashbox_type]:
                        if user in users_who_can_work_on_ct and user not in users_for_exchange.keys():
                            users_for_exchange[user] = []
                            if dttm in dttm_sections:
                                users_for_exchange[user].append(get_key_by_value(CHANGE_TYPE_CHOICES, 'FROM OTHER SPEC'))
                            elif check_time_is_between_boarders(dttm.time(), time_borders) == 'morning':
                                users_for_exchange[user].append(get_key_by_value(CHANGE_TYPE_CHOICES, 'FROM MORN'))
                            else:
                                users_for_exchange[user].append(get_key_by_value(CHANGE_TYPE_CHOICES, 'FROM EVEN'))
                            users_for_exchange[user].append(cashbox_type)
                else:
                    users_for_exchange = {k: v for k, v in users_for_exchange.items() if v[1] != cashbox_type}


    print(users_for_exchange)

    return JsonResponse.success()
