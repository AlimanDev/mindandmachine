import datetime
from django.db.models import Q, F, Sum
# from django.db.models.functions import Coalesce
from src.db.models import (
    WorkerDay,
    User,
    WorkType,
    WorkerCashboxInfo,
    WorkerDayCashboxDetails,
    PeriodClients,
    ProductionMonth,
    Shop,
)
from src.util.collection import group_by
from src.util.models_converter import BaseConverter
from decimal import Decimal
from ..utils import dttm_combine
from src.main.timetable.table.utils import count_work_month_stats
import numpy as np

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


def count_diff(dttm, period_clients, demand_ind, mean_bills_per_step, work_types):
    """
    Функция, которая считает нехватку

    Args:
        dttm(datetime.datetime): время на которое считать
        period_demands(PeriodDemand QuerySet): список PeriodDemand'ов
        demand_ind(int): индекс
        mean_bills_per_step:
        work_types(dict): словарь типов касс. по ключу -- id типа, по значению -- объект
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
    #     work_type_id__in=work_types.keys()
    # ).values('work_type_id').annotate(speed_usual=Max('mean_speed'))
    # mean_bills_per_step = {m['work_type_id']: m['speed_usual'] for m in mean_bills_per_step}
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
        for ind_shift in range(len(work_types)):
            ind = demand_ind + ind_shift
            if (ind < dem_len) and (period_clients[ind].dttm_forecast == dttm):
                ct_id = period_clients[ind].operation_type.work_type_id
                if ct_id in work_types.keys():
                    need_amount_dict[ct_id] = period_clients[ind].value / mean_bills_per_step[ct_id]

    return need_amount_dict, demand_ind


def get_worker_timetable2(shop_id, form, indicators_only=False, consider_vacancies=False):
    def dttm2index(dt_init, dttm, period_in_day, period_lengths_minutes):
        days = (dttm.date() - dt_init).days
        return days * period_in_day + (dttm.hour * 60 + dttm.minute) // period_lengths_minutes

    def fill_array(array, db_list, lambda_get_indexes, lambda_add):
        for db_model in db_list:
            array[lambda_get_indexes(db_model)] += lambda_add(db_model)

    MINUTES_IN_DAY = 24 * 60
    shop = Shop.objects.get(id=shop_id)
    period_lengths_minutes = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute
    period_in_day = MINUTES_IN_DAY // period_lengths_minutes
    absenteeism_coef = 1 + shop.absenteeism / 100

    from_dt = form['from_dt']
    # To include last day in "x < to_dt" conds
    to_dt = form['to_dt'] + datetime.timedelta(days=1)

    dttms = [
        datetime.datetime.combine(from_dt + datetime.timedelta(days=day), datetime.time(
            hour=period * period_lengths_minutes // 60,
            minute=period * period_lengths_minutes % 60)
        )
        for day in range((to_dt - from_dt).days)
        for period in range(MINUTES_IN_DAY // period_lengths_minutes)
    ]

    predict_needs = np.zeros(len(dttms))
    fact_needs = np.zeros(len(dttms))
    init_work = np.zeros(len(dttms))
    finite_work = np.zeros(len(dttms))

    # check cashboxes
    work_types = WorkType.objects.filter(shop_id=shop_id).order_by('id')
    if 'work_type_ids' in form and len(form['work_type_ids']) > 0:
        work_types = work_types.filter(id__in=form['work_type_ids'])
        if len(work_types) != len(form['work_type_ids']):
            return 'bad work_type_ids'
    work_types = group_by(work_types, group_key=lambda x: x.id)

    # query selecting PeriodClients
    need_workers = PeriodClients.objects.annotate(
        need_workers=F('value') * F('operation_type__speed_coef') / period_lengths_minutes,
    ).select_related('operation_type').filter(
        dttm_forecast__gte=from_dt,
        dttm_forecast__lte=to_dt,
        operation_type__work_type_id__in=work_types.keys(),
        operation_type__dttm_deleted__isnull=True,
    )

    lambda_index_periodclients = lambda x: [dttm2index(from_dt, x.dttm_forecast, period_in_day, period_lengths_minutes)]
    lambda_add_periodclients = lambda x: x.need_workers

    fill_array(
        predict_needs,
        need_workers.filter(type=PeriodClients.LONG_FORECASE_TYPE),
        lambda_index_periodclients,
        lambda_add_periodclients,
    )
    predict_needs = absenteeism_coef * predict_needs

    fill_array(
        fact_needs,
        need_workers.filter(type=PeriodClients.FACT_TYPE),
        lambda_index_periodclients,
        lambda_add_periodclients,
    )

    # query selecting cashbox_details
    status_list = list(WorkerDayCashboxDetails.WORK_TYPES_LIST)
    if consider_vacancies:
        status_list.append(WorkerDayCashboxDetails.TYPE_VACANCY)

    cashbox_details = WorkerDayCashboxDetails.objects.filter(
        Q(worker_day__worker__dt_fired__gt=to_dt) | Q(worker_day__worker__dt_fired__isnull=True),
        Q(worker_day__worker__dt_hired__lt=from_dt) | Q(worker_day__worker__dt_hired__isnull=True),
        dttm_from__gte=from_dt,
        dttm_to__lte=to_dt,
        work_type_id__in=work_types.keys(),
        status__in=status_list
    ).select_related('worker_day', 'worker_day__worker')

    lambda_index_work_details = lambda x: list(range(
            dttm2index(from_dt, x.dttm_from, period_in_day, period_lengths_minutes),
            dttm2index(from_dt, x.dttm_to, period_in_day, period_lengths_minutes),
        ))
    lambda_add_work_details = lambda x: 1

    fill_array(
        init_work,
        cashbox_details.filter(worker_day__parent_worker_day__isnull=True),
        lambda_index_work_details,
        lambda_add_work_details,
    )

    workers = list(User.objects.filter(id__in=cashbox_details.values_list('worker_day__worker')))
    month_work_stat = count_work_month_stats(
        dt_start=from_dt,
        dt_end=form['to_dt'], # original date
        users=workers
    )
    fot = 0
    norm_work_hours = ProductionMonth.objects.get(dt_first=from_dt.replace(day=1)).norm_work_hours
    for worker_id in month_work_stat.keys():
        fot += round(
            Decimal(month_work_stat[worker_id]['paid_hours']) *
            list(filter(lambda x: x.id == worker_id, workers))[0].salary / Decimal(norm_work_hours)
        )

    finite_workdetails = list(cashbox_details.filter(worker_day__child__id__isnull=True).select_related('worker_day'))
    fill_array(
        finite_work,
        finite_workdetails,
        lambda_index_work_details,
        lambda_add_work_details,
    )

    # if consider_vacancies:
    #     vacancies_workdetails = WorkerDayCashboxDetails.objects.filter(
    #         dttm_from__gte=from_dt,
    #         dttm_to__lte=to_dt,
    #         status=WorkerDayCashboxDetails.TYPE_VACANCY,
    #         work_type_id__in=work_types.keys(),
    #     )
    #     fill_array(
    #         finite_work,
    #         vacancies_workdetails,
    #         lambda_index_work_details,
    #         lambda_add_work_details,
    #     )

    response = {}

    if not indicators_only:
        real_cashiers = []
        real_cashiers_initial = []
        fact_cashier_needs = []
        predict_cashier_needs = []
        lack_of_cashiers_on_period = []
        for index, dttm in enumerate(dttms):
            dttm_converted = BaseConverter.convert_datetime(dttm)
            real_cashiers.append({'dttm': dttm_converted, 'amount': finite_work[index]})
            real_cashiers_initial.append({'dttm': dttm_converted,'amount': init_work[index]})
            fact_cashier_needs.append({'dttm': dttm_converted, 'amount': fact_needs[index]})
            predict_cashier_needs.append({'dttm': dttm_converted, 'amount': predict_needs[index]})
            lack_of_cashiers_on_period.append({
                'dttm': dttm_converted,
                'lack_of_cashiers': max(0,  predict_needs[index] - finite_work[index])
            })
        response = {
            'period_step': period_lengths_minutes,
            'tt_periods': {
                'real_cashiers': real_cashiers,
                'real_cashiers_initial': real_cashiers_initial,
                'predict_cashier_needs': predict_cashier_needs,
                'fact_cashier_needs': fact_cashier_needs,
            },
            'lack_of_cashiers_on_period': lack_of_cashiers_on_period
        }

    # statistics
    worker_amount = len(set([x.worker_day.worker_id for x in finite_workdetails if x.worker_day]))
    deadtime_part = round(100 * np.maximum(finite_work - predict_needs, 0).sum() / (finite_work.sum() +1e-8), 1)
    covering_part = round(100 * np.maximum(predict_needs - finite_work, 0).sum() / (predict_needs.sum() +1e-8), 1)
    days_diff = (predict_needs - finite_work).reshape(period_in_day, -1).sum(1) / (period_in_day / 3) # in workers
    need_cashier_amount = np.maximum(days_diff[np.argsort(days_diff)[-1:]], 0).sum() # todo: redo with logic

    revenue = 1000000
    response.update({
        'indicators': {
            'deadtime_part': deadtime_part,
            'cashier_amount': worker_amount,  # len(users_amount_set),
            'FOT': fot if fot else None,
            'need_cashier_amount': need_cashier_amount,  # * 1.4
            'revenue': revenue,
            'fot_revenue': round(fot / revenue, 2) * 100,
            # 'change_amount': changed_amount,
            'covering_part': covering_part,
        },
    })
    return response


# def get_worker_timetable(shop_id, form):
#     shop = Shop.objects.get(id=shop_id)
#     PERIOD_MINUTES = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute
#     PERIOD_STEP = datetime.timedelta(minutes=PERIOD_MINUTES)
#     TOTAL_PERIOD_SECONDS = PERIOD_STEP.total_seconds()
#
#     # get data from db
#     work_types = WorkType.objects.filter(shop_id=shop_id).order_by('id')
#     if len(form['work_type_ids']) > 0:
#         work_types = work_types.filter(id__in=form['work_type_ids'])
#         if len(work_types) != len(form['work_type_ids']):
#             return 'bad work_type_ids'  # todo: aa:fix bad code - raise standart error bad idea(could new error_type)
#     work_types = group_by(work_types, group_key=lambda x: x.id)
#
#     if len(form['work_type_ids']) == 0:
#         work_types_hard = WorkType.objects.filter(shop_id=shop_id, is_main_type=True)
#         if not work_types_hard:
#             work_types_hard = WorkType.objects.filter(
#                 shop_id=shop_id,
#                 do_forecast=WorkType.FORECAST_HARD
#             )[:1]
#     else:
#         work_types_hard = WorkType.objects.filter(
#             shop_id=shop_id,
#             id__in=form['work_type_ids'],
#             do_forecast=WorkType.FORECAST_HARD
#         )
#     # work_types_hard = []
#     # for work_type in work_types.values():
#     #     if work_type[0].do_forecast == WorkType.FORECAST_HARD:
#     #         work_types_hard.append(work_type[0])
#     work_types_hard = group_by(work_types_hard, group_key=lambda x: x.id)
#
#     work_types_main = []
#     for work_type in work_types.values():
#         if work_type[0].is_main_type:
#             work_types_main.append(work_type[0])
#     work_types_main = group_by(work_types_main, group_key=lambda x: x.id)
#
#     for ind in range(1, len(work_types) - len(work_types_main) + 1):
#         work_types_main[-ind] = None
#
#     worker_day_cashbox_detail_filter = {
#         'worker_day__dt__gte': form['from_dt'],
#         'worker_day__dt__lte': form['to_dt'],
#         'work_type_id__in': work_types.keys(),
#         'dttm_to__isnull': False,
#     }
#     if form['position_id']:
#         worker_day_cashbox_detail_filter['worker_day__worker__position_id'] = form['position_id']
#
#     cashbox_details_current = WorkerDayCashboxDetails.objects.qos_current_version().filter(
#         Q(worker_day__worker__dt_fired__gt=form['to_dt']) | Q(worker_day__worker__dt_fired__isnull=True),
#         Q(worker_day__worker__dt_hired__lt=form['from_dt']) | Q(worker_day__worker__dt_fired__isnull=True),
#         **worker_day_cashbox_detail_filter,
#     ).exclude(
#         status=WorkerDayCashboxDetails.TYPE_BREAK
#     ).order_by(
#         'worker_day__dt',
#         'dttm_from',
#         'dttm_to',
#     )
#     cashbox_details_initial = WorkerDayCashboxDetails.objects.qos_initial_version().filter(
#         Q(worker_day__worker__dt_fired__gt=form['to_dt']) | Q(worker_day__worker__dt_fired__isnull=True),
#         Q(worker_day__worker__dt_hired__lt=form['from_dt']) | Q(worker_day__worker__dt_fired__isnull=True),
#         **worker_day_cashbox_detail_filter,
#     ).exclude(
#         status=WorkerDayCashboxDetails.TYPE_BREAK
#     ).order_by(
#         'worker_day__dt',
#         'dttm_from',
#         'dttm_to',
#     )
#
#     worker_cashbox_info = list(WorkerCashboxInfo.objects.select_related('worker').filter(
#         Q(worker__dt_fired__gt=form['to_dt']) | Q(worker__dt_fired__isnull=True),
#         Q(worker__dt_hired__lt=form['from_dt']) | Q(worker__dt_fired__isnull=True),
#         is_active=True,
#         worker__workerday__dt__gte=form['from_dt'],
#         worker__workerday__dt__lte=form['to_dt'],
#         work_type_id__in=work_types.keys()
#     ).distinct())
#
#     # mean_bills_per_step = WorkerCashboxInfo.objects.filter(
#     #     is_active=True,
#     #     work_type_id__in=work_types.keys()
#     # ).values('work_type_id').annotate(speed_usual=Coalesce(Avg('mean_speed'), 1))
#     # mean_bills_per_step = {m['work_type_id']: m['speed_usual'] for m in mean_bills_per_step}
#
#     mean_bills_per_step = {m: PERIOD_MINUTES / work_types[m][0].speed_coef for m in work_types.keys()}
#
#     worker_amount = len(set([w.worker_id for w in worker_cashbox_info]))
#     worker_cashbox_info = group_by(
#         worker_cashbox_info,
#         group_key=lambda x: (x.worker_id, x.work_type_id)
#     )
#
#     period_clients = PeriodClients.objects.filter(
#         work_type__shop_id=shop_id,
#         dttm_forecast__gte=form['from_dt'],
#         dttm_forecast__lte=form['to_dt'] + datetime.timedelta(days=1),
#         type__in=[
#             PeriodClients.LONG_FORECASE_TYPE,
#             PeriodClients.FACT_TYPE,
#         ],
#         work_type_id__in=work_types.keys()
#     ).order_by(
#         '-type',
#         'dttm_forecast',
#         'work_type_id'
#     )
#
#     # supershop = SuperShop.objects.get(shop__id=shop_id)
#
#     # init data
#     real_cashiers = []  # текущее расписание (с изменениями)
#     real_cashiers_initial = []  # составленное алгоритмом
#     predict_cashier_needs = []
#     fact_cashier_needs = []
#     lack_of_cashiers_on_period = {}
#     for work_type in work_types:
#         lack_of_cashiers_on_period[work_type] = []
#     dttm_start = datetime.datetime.combine(form['from_dt'], datetime.time(3, 0))
#     periods = 48
#     # dttm_start = datetime.combine(form['from_dt'], supershop.tm_start) - PERIOD_STEP
#     # periods = int(timediff(supershop.tm_start, supershop.tm_end) * 2 + 0.99999) + 5 # period 30 minutes
#
#     time_borders = [
#         [datetime.time(6, 30), datetime.time(12, 00), 'morning'],
#         [datetime.time(18, 00), datetime.time(22, 30), 'evening'],
#     ]
#
#     ind_b_current = 0
#     ind_b_initial = 0
#     demand_ind = 0
#     fact_ind = 0
#     idle_time_numerator = 0
#     idle_time_denominator = 0
#     covering_time_numerator = 0
#     covering_time_denominator = 0
#     cashiers_lack_on_period_morning = []
#     cashiers_lack_on_period_evening = []
#
#     edge_ind = 0
#     while (edge_ind < len(period_clients)) and (period_clients[edge_ind].type != PeriodClients.FACT_TYPE):
#         edge_ind += 1
#
#     predict_demand = period_clients[:edge_ind]
#     fact_demand = period_clients[edge_ind:]
#
#     wdcds_current = cashbox_details_current  # alias
#     wdcds_initial = cashbox_details_initial
#     wdcds_current_len = len(wdcds_current)
#     wdcds_initial_len = len(wdcds_initial)
#
#     for day_ind in range((form['to_dt'] - form['from_dt']).days):
#         each_day_morning = []
#         each_day_evening = []
#         for time_ind in range(periods):
#             dttm = dttm_start + datetime.timedelta(days=day_ind) + time_ind * PERIOD_STEP
#
#             dttm_end = dttm + PERIOD_STEP
#             dttm_ind_current = dttm - PERIOD_STEP
#             dttm_ind_initial = dttm - PERIOD_STEP
#
#             # cashier_working_now = []
#             # for cashier in cashiers_working_today:
#             #     if cashier.worker_day.tm_work_end > cashier.worker_day.tm_work_start:
#             #         if cashier.worker_day.tm_work_start <= dttm.time() and cashier.worker_day.tm_work_end >= dttm_end.time():
#             #             cashier_working_now.append(cashier)
#             #     else:
#             #         if cashier.worker_day.tm_work_start <= dttm.time():
#             #             cashier_working_now.append(cashier)
#             # todo: неправильно учитывается время от 23:30
#             # for cashier in cashier_working_now:
#             #     if cashier.work_type is not None:
#             #         cashiers_on_work_type[cashier.work_type.id] += 1  # shift to first model, which has intersection
#             while (ind_b_current < wdcds_current_len) and (dttm_ind_current <= dttm) and wdcds_current[
#                 ind_b_current].dttm_to:
#                 dttm_ind_current = dttm_combine(wdcds_current[ind_b_current].worker_day.dt,
#                                                 wdcds_current[ind_b_current].dttm_to.time())
#                 ind_b_current += 1
#             ind_b_current = ind_b_current - 1 if (dttm_ind_current > dttm) and ind_b_current else ind_b_current
#             while (ind_b_initial < wdcds_initial_len) and (dttm_ind_initial <= dttm) and wdcds_initial[
#                 ind_b_initial].dttm_to:
#                 dttm_ind_initial = dttm_combine(wdcds_initial[ind_b_initial].worker_day.dt,
#                                                 wdcds_initial[ind_b_initial].dttm_to.time())
#                 ind_b_initial += 1
#             ind_b_initial = ind_b_initial - 1 if (dttm_ind_initial > dttm) and ind_b_initial else ind_b_initial
#
#             ind_e_current = ind_b_current
#             ind_e_initial = ind_b_initial
#             period_bills = {i: 0 for i in work_types.keys()}
#             period_cashiers_current = 0.0
#             period_cashiers_initial = 0.0
#             period_cashiers_hard = 0.0
#
#             if ind_e_current < wdcds_current_len and wdcds_current[ind_e_current].dttm_to.time():
#                 dttm_ind_current = dttm_combine(wdcds_current[ind_e_current].worker_day.dt,
#                                                 wdcds_current[ind_e_current].dttm_from.time())
#                 dttm_ind_current_end = dttm_combine(wdcds_current[ind_e_current].worker_day.dt,
#                                                     wdcds_current[ind_e_current].dttm_to.time())
#
#             if ind_e_initial < wdcds_initial_len and wdcds_initial[ind_e_initial].dttm_to.time():
#                 dttm_ind_initial = dttm_combine(wdcds_initial[ind_e_initial].worker_day.dt,
#                                                 wdcds_initial[ind_e_initial].dttm_from.time())
#                 dttm_ind_initial_end = dttm_combine(wdcds_initial[ind_e_initial].worker_day.dt,
#                                                     wdcds_initial[ind_e_initial].dttm_to.time())
#
#             while (ind_e_current < wdcds_current_len) and (dttm_ind_current < dttm_end):
#                 if dttm_ind_current_end > dttm:
#                     proportion = min(
#                         (dttm_ind_current_end - dttm).total_seconds(),
#                         (dttm_end - dttm_ind_current).total_seconds(),
#                         TOTAL_PERIOD_SECONDS
#                     ) / TOTAL_PERIOD_SECONDS
#                     if wdcds_current[ind_e_current].worker_day.worker_id in worker_cashbox_info.keys():
#                         period_bills[wdcds_current[ind_e_current].work_type_id] += proportion * \
#                                                                                       (PERIOD_MINUTES /
#                                                                                        worker_cashbox_info[(
#                                                                                        wdcds_current[
#                                                                                            ind_e_current].worker_day.worker_id,
#                                                                                        wdcds_current[
#                                                                                            ind_e_current].work_type_id)][
#                                                                                            0].mean_speed)
#                     period_cashiers_current += 1 * proportion
#                     if wdcds_current[ind_e_current].work_type_id in work_types_main.keys():
#                         period_cashiers_hard += 1 * proportion
#
#                 ind_e_current += 1
#                 if ind_e_current < wdcds_current_len and wdcds_current[ind_e_current].dttm_to:
#                     dttm_ind_current = dttm_combine(wdcds_current[ind_e_current].worker_day.dt,
#                                                     wdcds_current[ind_e_current].dttm_from.time())
#                     dttm_ind_current_end = dttm_combine(wdcds_current[ind_e_current].worker_day.dt,
#                                                         wdcds_current[ind_e_current].dttm_to.time())
#
#             while (ind_e_initial < wdcds_initial_len) and (dttm_ind_initial < dttm_end):
#                 if dttm_ind_initial_end > dttm:
#                     proportion = min(
#                         (dttm_ind_initial_end - dttm).total_seconds(),
#                         (dttm_end - dttm_ind_initial).total_seconds(),
#                         TOTAL_PERIOD_SECONDS
#                     ) / TOTAL_PERIOD_SECONDS
#                     if wdcds_initial[ind_e_initial].worker_day.worker_id in worker_cashbox_info.keys():
#                         period_bills[wdcds_initial[ind_e_initial].work_type_id] += proportion * \
#                             (PERIOD_MINUTES / worker_cashbox_info[(wdcds_initial[ind_e_initial].worker_day.worker_id,
#                                                                    wdcds_initial[ind_e_initial].work_type_id)][0].mean_speed)
#                     period_cashiers_initial += 1 * proportion
#
#                 ind_e_initial += 1
#                 if ind_e_initial < wdcds_initial_len and wdcds_initial[ind_e_initial].dttm_to.time():
#                     dttm_ind_initial = dttm_combine(wdcds_initial[ind_e_initial].worker_day.dt,
#                                                     wdcds_initial[ind_e_initial].dttm_from.time())
#                     dttm_ind_initial_end = dttm_combine(wdcds_initial[ind_e_initial].worker_day.dt,
#                                                         wdcds_initial[ind_e_initial].dttm_to.time())
#
#             dttm_converted = BaseConverter.convert_datetime(dttm)
#             real_cashiers.append({
#                 'dttm': dttm_converted,
#                 'amount': period_cashiers_current
#             })
#
#             real_cashiers_initial.append({
#                 'dttm': dttm_converted,
#                 'amount': period_cashiers_initial
#             })
#
#             predict_diff_dict, demand_ind_2 = count_diff(dttm, predict_demand, demand_ind, mean_bills_per_step,
#                                                          work_types)
#             predict_cashier_needs.append({
#                 'dttm': dttm_converted,
#                 'amount': sum(predict_diff_dict.values()),
#             })
#
#             real_diff_dict, fact_ind = count_diff(dttm, fact_demand, fact_ind, mean_bills_per_step, work_types)
#             fact_cashier_needs.append({
#                 'dttm': dttm_converted,
#                 'amount': sum(real_diff_dict.values()),
#             })
#
#             # predict_diff_hard_dict, _ = count_diff(dttm, predict_demand, demand_ind, mean_bills_per_step, work_types_main)
#             difference_of_pred_real = period_cashiers_current - sum(predict_diff_dict.values())
#             if difference_of_pred_real > 0:
#                 idle_time_numerator += difference_of_pred_real
#             elif difference_of_pred_real < 0:
#                 covering_time_numerator += abs(difference_of_pred_real)
#                 covering_time_denominator += sum(predict_diff_dict.values())
#             idle_time_denominator += period_cashiers_current
#
#             demand_ind = demand_ind_2
#
#             need_amount_morning = 0
#             need_amount_evening = 0
#             # need_total = 0
#
#             for work_type in work_types:
#                 check_time = check_time_is_between_boarders(dttm.time(), time_borders)
#                 if work_type in work_types_main.keys():
#                     if check_time == 'morning':
#                         need_amount_morning += predict_diff_dict.get(work_type, 0)
#                     elif check_time == 'evening':
#                         need_amount_evening += predict_diff_dict.get(work_type, 0)
#                 if work_type in work_types.keys():
#                     # need_total += predict_diff_dict.get(work_type, 0)
#                     lack_of_cashiers_on_period[work_type].append({
#                         'lack_of_cashiers': max(0, sum(predict_diff_dict.values()) - period_cashiers_current),
#                         'dttm_start': dttm_converted,
#                     })
#
#             need_amount_morning = max(0, need_amount_morning - period_cashiers_hard)
#             need_amount_evening = max(0, need_amount_evening - period_cashiers_hard)
#
#             each_day_morning.append(need_amount_morning)
#             each_day_evening.append(need_amount_evening)
#
#         cashiers_lack_on_period_morning.append(max(each_day_morning))
#         cashiers_lack_on_period_evening.append(max(each_day_evening))
#
#     max_of_cashiers_lack_morning = max(cashiers_lack_on_period_morning)
#     max_of_cashiers_lack_evening = max(cashiers_lack_on_period_evening)
#
#     changed_amount = WorkerDay.objects.select_related('worker').filter(
#         dt__gte=form['from_dt'],
#         dt__lte=form['to_dt'],
#         worker__shop_id=shop_id,
#         worker__attachment_group=User.GROUP_STAFF,
#     ).count() - WorkerDay.objects.select_related('worker').filter(
#         dt__gte=form['from_dt'],
#         dt__lte=form['to_dt'],
#         worker__shop_id=shop_id,
#         parent_worker_day__isnull=True,
#         worker__attachment_group=User.GROUP_STAFF,
#     ).count()
#
#     response = {
#         'indicators': {
#             'deadtime_part': round(100 * idle_time_numerator / (idle_time_denominator + 1e-8), 1),
#             'big_demand_persent': 0,  # big_demand_persent,
#             'cashier_amount': worker_amount,  # len(users_amount_set),
#             'FOT': None,
#             'need_cashier_amount': round((max_of_cashiers_lack_morning + max_of_cashiers_lack_evening)),  # * 1.4
#             'change_amount': changed_amount,
#             'covering_part': round(100 * covering_time_numerator / (covering_time_denominator + 1e-8), 1)
#         },
#         'period_step': PERIOD_MINUTES,
#         'tt_periods': {
#             'real_cashiers': real_cashiers,
#             'real_cashiers_initial': real_cashiers_initial,
#             'predict_cashier_needs': predict_cashier_needs,
#             'fact_cashier_needs': fact_cashier_needs,
#         },
#         'lack_of_cashiers_on_period': lack_of_cashiers_on_period
#     }
#     return response
