from src.db.models import WorkerDay
from datetime import time, timedelta


def filter_worker_day_by_dttm(shop_id, day_type, dttm_from, dttm_to):
    dt_from = dttm_from.date()
    tm_from = dttm_from.time()
    dt_to = dttm_to.date()
    tm_to = dttm_to.time()

    days_raw = WorkerDay.objects.select_related('worker').filter(
        worker__shop_id=shop_id,
        type=day_type,
        dt__gte=dt_from,
        dt__lte=dt_to,
    )

    days = []
    for d in days_raw:
        if d.dt == dt_from and d.tm_work_end <= tm_from:
            continue
        if d.dt == dt_to and d.tm_work_start >= tm_to:
            continue

        days.append(d)

    return days


def check_time_is_between_boarders(tm, borders):
    """
    checks if time is in allowed boarders
    :param tm: datetime.time obj
    :param borders: [datetime.time(), datetime.time(), 'day type'] : 'day type': 'morning', 'evening'
    :return: day type if in borders else False
    """
    for border in borders:
        if border[0] < tm < border[1]:
            return border[2]
    return False


def count_diff(dttm, period_demands, demand_ind, mean_bills_per_step, cashbox_types, PERIOD_MINUTES = 30):
    # fixme: aa: work only if all steps are 30 minutes
    # todo: period_bills -- а они нужны вообще?
    # period_demand is sorted by dttm_forecast, so find the dttm
    # mean_bills_per_step = WorkerCashboxInfo.objects.filter(
    #     is_active=True,
    #     cashbox_type_id__in=cashbox_types.keys()
    # ).values('cashbox_type_id').annotate(speed_usual=Max('mean_speed'))
    # mean_bills_per_step = {m['cashbox_type_id']: m['speed_usual'] for m in mean_bills_per_step}
    # edge_ind = 0
    # while (edge_ind < len(period_demand)) and (period_demand[edge_ind].type != PeriodDemand.Type.FACT.value):
    #     edge_ind += 1
    #
    # period_demands = period_demand[:edge_ind]
    need_amount_dict = {}

    dem_len = len(period_demands)
    while (demand_ind < dem_len) and (period_demands[demand_ind].dttm_forecast < dttm):
        demand_ind += 1

    if demand_ind < dem_len:
        for ind_shift in range(len(cashbox_types)):
            ind = demand_ind + ind_shift
            if (ind < dem_len) and (period_demands[ind].dttm_forecast == dttm):
                ct_id = period_demands[ind].cashbox_type_id
                if ct_id in cashbox_types.keys():
                    need_amount_dict[ct_id] = period_demands[ind].clients / cashbox_types[ct_id][0].speed_coef \
                               / (PERIOD_MINUTES / mean_bills_per_step[ct_id])

    return need_amount_dict, demand_ind

