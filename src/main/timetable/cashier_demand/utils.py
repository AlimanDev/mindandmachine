from src.db.models import WorkerDay
from datetime import time, timedelta


def filter_worker_day_by_dttm(shop_id, day_type, dttm_from, dttm_to):
    """
    Ну, что-то она да делает

    Args:
        shop_id(int):
        day_type: ?
        dttm_from(datetime.datetime):
        dttm_to(datetime.datetime):

    """
    dt_from = dttm_from.date()
    tm_from = dttm_from.time()
    dt_to = dttm_to.date()
    tm_to = dttm_to.time()

    days_raw = WorkerDay.objects.filter(
        worker_shop_id=shop_id,
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
    Проверяет, что время в допустимых значениях borders

    Args:
        tm(datetime.time): время которое надо проверить
        borders(list): граница времени

    Examples:
        borders -- [[8:00, 12:00, 'morning'], [18:00, 22:00, 'evening']]

    Returns:
        Тип дня 'evening'/'morning', либо False если ни в один из промежутков не попадает
    """
    for border in borders:
        if border[0] < tm < border[1]:
            return border[2]
    return False


def count_diff(dttm, period_clients, demand_ind, mean_bills_per_step, cashbox_types, PERIOD_MINUTES = 30):
    """
    Функция, которая считает нехватку

    Args:
        dttm(datetime.datetime): время на которое считать
        period_demands(PeriodDemand QuerySet): список PeriodDemand'ов
        demand_ind(int): индекс
        mean_bills_per_step:
        cashbox_types(dict): словарь типов касс. по ключу -- id типа, по значению -- объект
        PERIOD_MINUTES(int):

    Returns:
        (tuple): tuple содержащий:
            need_amount_dict (dict): по ключу -- id типа кассы, по значению -- значение нехватки
            demand_ind (int): индекс для следующего вызова этой функции
    """
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

    dem_len = len(period_clients)
    while (demand_ind < dem_len) and (period_clients[demand_ind].dttm_forecast < dttm):
        demand_ind += 1

    if demand_ind < dem_len:
        for ind_shift in range(len(cashbox_types)):
            ind = demand_ind + ind_shift
            if (ind < dem_len) and (period_clients[ind].dttm_forecast == dttm):
                ct_id = period_clients[ind].cashbox_type_id
                if ct_id in cashbox_types.keys():
                    need_amount_dict[ct_id] = period_clients[ind].value / cashbox_types[ct_id][0].speed_coef \
                               / (PERIOD_MINUTES / mean_bills_per_step[ct_id])

    return need_amount_dict, demand_ind

