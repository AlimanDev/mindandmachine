from datetime import datetime, time, timedelta

from django.db.models import Q
# from django.db.models.functions import Coalesce
from src.db.models import (
    WorkerDay,
    User,
    CashboxType,
    WorkerCashboxInfo,
    WorkerDayCashboxDetails,
    PeriodClients,
    Shop,
)
from src.util.collection import group_by
from src.util.models_converter import BaseConverter
from ..utils import dttm_combine

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


def count_diff(dttm, period_clients, demand_ind, mean_bills_per_step, cashbox_types):
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
                    need_amount_dict[ct_id] = period_clients[ind].value / mean_bills_per_step[ct_id]

    return need_amount_dict, demand_ind


def get_worker_timetable(shop_id, form):
    shop = Shop.objects.get(id=shop_id)
    PERIOD_MINUTES = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute
    PERIOD_STEP = timedelta(minutes=PERIOD_MINUTES)
    TOTAL_PERIOD_SECONDS = PERIOD_STEP.total_seconds()

    # get data from db
    cashbox_types = CashboxType.objects.filter(shop_id=shop_id).order_by('id')
    if len(form['cashbox_type_ids']) > 0:
        cashbox_types = cashbox_types.filter(id__in=form['cashbox_type_ids'])
        if len(cashbox_types) != len(form['cashbox_type_ids']):
            return 'bad cashbox_type_ids'  # todo: aa:fix bad code - raise standart error bad idea(could new error_type)
    cashbox_types = group_by(cashbox_types, group_key=lambda x: x.id)

    if len(form['cashbox_type_ids']) == 0:
        cashbox_types_hard = CashboxType.objects.filter(shop_id=shop_id, is_main_type=True)
        if not cashbox_types_hard:
            cashbox_types_hard = CashboxType.objects.filter(
                shop_id=shop_id,
                do_forecast=CashboxType.FORECAST_HARD
            )[:1]
    else:
        cashbox_types_hard = CashboxType.objects.filter(
            shop_id=shop_id,
            id__in=form['cashbox_type_ids'],
            do_forecast=CashboxType.FORECAST_HARD
        )
    # cashbox_types_hard = []
    # for cashbox_type in cashbox_types.values():
    #     if cashbox_type[0].do_forecast == CashboxType.FORECAST_HARD:
    #         cashbox_types_hard.append(cashbox_type[0])
    cashbox_types_hard = group_by(cashbox_types_hard, group_key=lambda x: x.id)

    cashbox_types_main = []
    for cashbox_type in cashbox_types.values():
        if cashbox_type[0].is_main_type:
            cashbox_types_main.append(cashbox_type[0])
    cashbox_types_main = group_by(cashbox_types_main, group_key=lambda x: x.id)

    for ind in range(1, len(cashbox_types) - len(cashbox_types_main) + 1):
        cashbox_types_main[-ind] = None

    worker_day_cashbox_detail_filter = {
        'worker_day__dt__gte': form['from_dt'],
        'worker_day__dt__lte': form['to_dt'],
        'cashbox_type_id__in': cashbox_types.keys(),
        'dttm_to__isnull': False,
    }
    if form['position_id']:
        worker_day_cashbox_detail_filter['worker_day__worker__position_id'] = form['position_id']

    cashbox_details_current = WorkerDayCashboxDetails.objects.qos_current_version().filter(
        Q(worker_day__worker__dt_fired__gt=form['to_dt']) | Q(worker_day__worker__dt_fired__isnull=True),
        Q(worker_day__worker__dt_hired__lt=form['from_dt']) | Q(worker_day__worker__dt_fired__isnull=True),
        **worker_day_cashbox_detail_filter,
    ).exclude(
        status=WorkerDayCashboxDetails.TYPE_BREAK
    ).order_by(
        'worker_day__dt',
        'dttm_from',
        'dttm_to',
    )
    cashbox_details_initial = WorkerDayCashboxDetails.objects.qos_initial_version().filter(
        Q(worker_day__worker__dt_fired__gt=form['to_dt']) | Q(worker_day__worker__dt_fired__isnull=True),
        Q(worker_day__worker__dt_hired__lt=form['from_dt']) | Q(worker_day__worker__dt_fired__isnull=True),
        **worker_day_cashbox_detail_filter,
    ).exclude(
        status=WorkerDayCashboxDetails.TYPE_BREAK
    ).order_by(
        'worker_day__dt',
        'dttm_from',
        'dttm_to',
    )

    worker_cashbox_info = list(WorkerCashboxInfo.objects.select_related('worker').filter(
        Q(worker__dt_fired__gt=form['to_dt']) | Q(worker__dt_fired__isnull=True),
        Q(worker__dt_hired__lt=form['from_dt']) | Q(worker__dt_fired__isnull=True),
        is_active=True,
        worker__workerday__dt__gte=form['from_dt'],
        worker__workerday__dt__lte=form['to_dt'],
        cashbox_type_id__in=cashbox_types.keys()
    ).distinct())

    # mean_bills_per_step = WorkerCashboxInfo.objects.filter(
    #     is_active=True,
    #     cashbox_type_id__in=cashbox_types.keys()
    # ).values('cashbox_type_id').annotate(speed_usual=Coalesce(Avg('mean_speed'), 1))
    # mean_bills_per_step = {m['cashbox_type_id']: m['speed_usual'] for m in mean_bills_per_step}

    mean_bills_per_step = {m: PERIOD_MINUTES / cashbox_types[m][0].speed_coef for m in cashbox_types.keys()}
    print(mean_bills_per_step)

    worker_amount = len(set([w.worker_id for w in worker_cashbox_info]))
    worker_cashbox_info = group_by(
        worker_cashbox_info,
        group_key=lambda x: (x.worker_id, x.cashbox_type_id)
    )

    period_clients = PeriodClients.objects.filter(
        cashbox_type__shop_id=shop_id,
        dttm_forecast__gte=form['from_dt'],
        dttm_forecast__lte=form['to_dt'] + timedelta(days=1),
        type__in=[
            PeriodClients.LONG_FORECASE_TYPE,
            PeriodClients.FACT_TYPE,
        ],
        cashbox_type_id__in=cashbox_types.keys()
    ).order_by(
        'type',
        'dttm_forecast',
        'cashbox_type_id'
    )

    # supershop = SuperShop.objects.get(shop__id=shop_id)

    # init data
    real_cashiers = []  # текущее расписание (с изменениями)
    real_cashiers_initial = []  # составленное алгоритмом
    predict_cashier_needs = []
    fact_cashier_needs = []
    lack_of_cashiers_on_period = {}
    for cashbox_type in cashbox_types:
        lack_of_cashiers_on_period[cashbox_type] = []
    dttm_start = datetime.combine(form['from_dt'], time(3, 0))
    periods = 48
    # dttm_start = datetime.combine(form['from_dt'], supershop.tm_start) - PERIOD_STEP
    # periods = int(timediff(supershop.tm_start, supershop.tm_end) * 2 + 0.99999) + 5 # period 30 minutes

    time_borders = [
        [time(6, 30), time(12, 00), 'morning'],
        [time(18, 00), time(22, 30), 'evening'],
    ]

    ind_b_current = 0
    ind_b_initial = 0
    demand_ind = 0
    fact_ind = 0
    idle_time_numerator = 0
    idle_time_denominator = 0
    covering_time_numerator = 0
    covering_time_denominator = 0
    cashiers_lack_on_period_morning = []
    cashiers_lack_on_period_evening = []

    edge_ind = 0
    while (edge_ind < len(period_clients)) and (period_clients[edge_ind].type != PeriodClients.FACT_TYPE):
        edge_ind += 1

    predict_demand = period_clients[:edge_ind]
    fact_demand = period_clients[edge_ind:]

    wdcds_current = cashbox_details_current  # alias
    wdcds_initial = cashbox_details_initial
    wdcds_current_len = len(wdcds_current)
    wdcds_initial_len = len(wdcds_initial)

    for day_ind in range((form['to_dt'] - form['from_dt']).days):
        each_day_morning = []
        each_day_evening = []
        for time_ind in range(periods):
            dttm = dttm_start + timedelta(days=day_ind) + time_ind * PERIOD_STEP

            dttm_end = dttm + PERIOD_STEP
            dttm_ind_current = dttm - PERIOD_STEP
            dttm_ind_initial = dttm - PERIOD_STEP

            # cashier_working_now = []
            # for cashier in cashiers_working_today:
            #     if cashier.worker_day.tm_work_end > cashier.worker_day.tm_work_start:
            #         if cashier.worker_day.tm_work_start <= dttm.time() and cashier.worker_day.tm_work_end >= dttm_end.time():
            #             cashier_working_now.append(cashier)
            #     else:
            #         if cashier.worker_day.tm_work_start <= dttm.time():
            #             cashier_working_now.append(cashier)
            # todo: неправильно учитывается время от 23:30
            # for cashier in cashier_working_now:
            #     if cashier.cashbox_type is not None:
            #         cashiers_on_cashbox_type[cashier.cashbox_type.id] += 1  # shift to first model, which has intersection
            while (ind_b_current < wdcds_current_len) and (dttm_ind_current <= dttm) and wdcds_current[
                ind_b_current].dttm_to:
                dttm_ind_current = dttm_combine(wdcds_current[ind_b_current].worker_day.dt,
                                                wdcds_current[ind_b_current].dttm_to.time())
                ind_b_current += 1
            ind_b_current = ind_b_current - 1 if (dttm_ind_current > dttm) and ind_b_current else ind_b_current
            while (ind_b_initial < wdcds_initial_len) and (dttm_ind_initial <= dttm) and wdcds_initial[
                ind_b_initial].dttm_to:
                dttm_ind_initial = dttm_combine(wdcds_initial[ind_b_initial].worker_day.dt,
                                                wdcds_initial[ind_b_initial].dttm_to.time())
                ind_b_initial += 1
            ind_b_initial = ind_b_initial - 1 if (dttm_ind_initial > dttm) and ind_b_initial else ind_b_initial

            ind_e_current = ind_b_current
            ind_e_initial = ind_b_initial
            period_bills = {i: 0 for i in cashbox_types.keys()}
            period_cashiers_current = 0.0
            period_cashiers_initial = 0.0
            period_cashiers_hard = 0.0

            if ind_e_current < wdcds_current_len and wdcds_current[ind_e_current].dttm_to.time():
                dttm_ind_current = dttm_combine(wdcds_current[ind_e_current].worker_day.dt,
                                                wdcds_current[ind_e_current].dttm_from.time())
                dttm_ind_current_end = dttm_combine(wdcds_current[ind_e_current].worker_day.dt,
                                                    wdcds_current[ind_e_current].dttm_to.time())

            if ind_e_initial < wdcds_initial_len and wdcds_initial[ind_e_initial].dttm_to.time():
                dttm_ind_initial = dttm_combine(wdcds_initial[ind_e_initial].worker_day.dt,
                                                wdcds_initial[ind_e_initial].dttm_from.time())
                dttm_ind_initial_end = dttm_combine(wdcds_initial[ind_e_initial].worker_day.dt,
                                                    wdcds_initial[ind_e_initial].dttm_to.time())

            while (ind_e_current < wdcds_current_len) and (dttm_ind_current < dttm_end):
                if dttm_ind_current_end > dttm:
                    proportion = min(
                        (dttm_ind_current_end - dttm).total_seconds(),
                        (dttm_end - dttm_ind_current).total_seconds(),
                        TOTAL_PERIOD_SECONDS
                    ) / TOTAL_PERIOD_SECONDS
                    if wdcds_current[ind_e_current].worker_day.worker_id in worker_cashbox_info.keys():
                        period_bills[wdcds_current[ind_e_current].cashbox_type_id] += proportion * \
                                                                                      (PERIOD_MINUTES /
                                                                                       worker_cashbox_info[(
                                                                                       wdcds_current[
                                                                                           ind_e_current].worker_day.worker_id,
                                                                                       wdcds_current[
                                                                                           ind_e_current].cashbox_type_id)][
                                                                                           0].mean_speed)
                    period_cashiers_current += 1 * proportion
                    if wdcds_current[ind_e_current].cashbox_type_id in cashbox_types_main.keys():
                        period_cashiers_hard += 1 * proportion

                ind_e_current += 1
                if ind_e_current < wdcds_current_len and wdcds_current[ind_e_current].dttm_to:
                    dttm_ind_current = dttm_combine(wdcds_current[ind_e_current].worker_day.dt,
                                                    wdcds_current[ind_e_current].dttm_from.time())
                    dttm_ind_current_end = dttm_combine(wdcds_current[ind_e_current].worker_day.dt,
                                                        wdcds_current[ind_e_current].dttm_to.time())

            while (ind_e_initial < wdcds_initial_len) and (dttm_ind_initial < dttm_end):
                if dttm_ind_initial_end > dttm:
                    proportion = min(
                        (dttm_ind_initial_end - dttm).total_seconds(),
                        (dttm_end - dttm_ind_initial).total_seconds(),
                        TOTAL_PERIOD_SECONDS
                    ) / TOTAL_PERIOD_SECONDS
                    if wdcds_initial[ind_e_initial].worker_day.worker_id in worker_cashbox_info.keys():
                        period_bills[wdcds_initial[ind_e_initial].cashbox_type_id] += proportion * \
                            (PERIOD_MINUTES / worker_cashbox_info[(wdcds_initial[ind_e_initial].worker_day.worker_id,
                                                                   wdcds_initial[ind_e_initial].cashbox_type_id)][0].mean_speed)
                    period_cashiers_initial += 1 * proportion

                ind_e_initial += 1
                if ind_e_initial < wdcds_initial_len and wdcds_initial[ind_e_initial].dttm_to.time():
                    dttm_ind_initial = dttm_combine(wdcds_initial[ind_e_initial].worker_day.dt,
                                                    wdcds_initial[ind_e_initial].dttm_from.time())
                    dttm_ind_initial_end = dttm_combine(wdcds_initial[ind_e_initial].worker_day.dt,
                                                        wdcds_initial[ind_e_initial].dttm_to.time())

            dttm_converted = BaseConverter.convert_datetime(dttm)
            real_cashiers.append({
                'dttm': dttm_converted,
                'amount': period_cashiers_current
            })

            real_cashiers_initial.append({
                'dttm': dttm_converted,
                'amount': period_cashiers_initial
            })

            predict_diff_dict, demand_ind_2 = count_diff(dttm, predict_demand, demand_ind, mean_bills_per_step,
                                                         cashbox_types)
            predict_cashier_needs.append({
                'dttm': dttm_converted,
                'amount': sum(predict_diff_dict.values()),
            })

            real_diff_dict, fact_ind = count_diff(dttm, fact_demand, fact_ind, mean_bills_per_step, cashbox_types)
            fact_cashier_needs.append({
                'dttm': dttm_converted,
                'amount': sum(real_diff_dict.values()),
            })

            # predict_diff_hard_dict, _ = count_diff(dttm, predict_demand, demand_ind, mean_bills_per_step, cashbox_types_main)
            difference_of_pred_real = period_cashiers_current - sum(predict_diff_dict.values())
            if difference_of_pred_real > 0:
                idle_time_numerator += difference_of_pred_real
            elif difference_of_pred_real < 0:
                covering_time_numerator += abs(difference_of_pred_real)
                covering_time_denominator += sum(predict_diff_dict.values())
            idle_time_denominator += period_cashiers_current

            demand_ind = demand_ind_2

            need_amount_morning = 0
            need_amount_evening = 0
            # need_total = 0

            for cashbox_type in cashbox_types:
                check_time = check_time_is_between_boarders(dttm.time(), time_borders)
                if cashbox_type in cashbox_types_main.keys():
                    if check_time == 'morning':
                        need_amount_morning += predict_diff_dict.get(cashbox_type, 0)
                    elif check_time == 'evening':
                        need_amount_evening += predict_diff_dict.get(cashbox_type, 0)
                if cashbox_type in cashbox_types.keys():
                    # need_total += predict_diff_dict.get(cashbox_type, 0)
                    lack_of_cashiers_on_period[cashbox_type].append({
                        'lack_of_cashiers': max(0, sum(predict_diff_dict.values()) - period_cashiers_current),
                        'dttm_start': dttm_converted,
                    })

            need_amount_morning = max(0, need_amount_morning - period_cashiers_hard)
            need_amount_evening = max(0, need_amount_evening - period_cashiers_hard)

            each_day_morning.append(need_amount_morning)
            each_day_evening.append(need_amount_evening)

        cashiers_lack_on_period_morning.append(max(each_day_morning))
        cashiers_lack_on_period_evening.append(max(each_day_evening))

    max_of_cashiers_lack_morning = max(cashiers_lack_on_period_morning)
    max_of_cashiers_lack_evening = max(cashiers_lack_on_period_evening)

    changed_amount = WorkerDay.objects.select_related('worker').filter(
        dt__gte=form['from_dt'],
        dt__lte=form['to_dt'],
        worker__shop_id=shop_id,
        worker__attachment_group=User.GROUP_STAFF,
    ).count() - WorkerDay.objects.select_related('worker').filter(
        dt__gte=form['from_dt'],
        dt__lte=form['to_dt'],
        worker__shop_id=shop_id,
        parent_worker_day__isnull=True,
        worker__attachment_group=User.GROUP_STAFF,
    ).count()

    response = {
        'indicators': {
            'deadtime_part': round(100 * idle_time_numerator / (idle_time_denominator + 1e-8), 1),
            'big_demand_persent': 0,  # big_demand_persent,
            'cashier_amount': worker_amount,  # len(users_amount_set),
            'FOT': None,
            'need_cashier_amount': round((max_of_cashiers_lack_morning + max_of_cashiers_lack_evening)),  # * 1.4
            'change_amount': changed_amount,
            'covering_part': round(100 * covering_time_numerator / (covering_time_denominator + 1e-8), 1)
        },
        'period_step': PERIOD_MINUTES,
        'tt_periods': {
            'real_cashiers': real_cashiers,
            'real_cashiers_initial': real_cashiers_initial,
            'predict_cashier_needs': predict_cashier_needs,
            'fact_cashier_needs': fact_cashier_needs,
        },
        'lack_of_cashiers_on_period': lack_of_cashiers_on_period
    }
    return response