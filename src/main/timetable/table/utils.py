from src.base.models import (
    Employment,
    Shop,
)
from src.timetable.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    ProductionDay,
)
import json
from datetime import time
import datetime as dt
from django.db.models import Sum, Q, Count
from django.db.models.functions import Coalesce

from src.util.models_converter import WorkerDayConverter
from src.main.urv.utils import wd_stat_count

def count_work_month_stats(shop, dt_start, dt_end, employments, times_borders=None):
    """
    Функция для посчета статистики работника за месяц

    Args:
         dt_start(datetime.date): дата начала подсчета
         dt_end(datetime.date): дата конца подсчета
         employments(QuerySet): список пользователей для которых считать
    """
    def get_norm_work_periods(days, dt_start, dt_end):
        norm = {
            'days': 0,
            'hours': 0,
        }
        for day in days[dt_start.day - 1: dt_end.day]:
            if day.type in ProductionDay.WORK_TYPES:
                norm['days'] += 1
                norm['hours'] += ProductionDay.WORK_NORM_HOURS[day.type]
        return norm

    def init_values(times_borders, norm_days):
        dict = {
            'hours_fact': 0,
            'paid_days': 0,
            'paid_hours': 0.0,
            'diff_norm_days': norm_days['days'],
            'diff_norm_hours': norm_days['hours'],
            'work_in_holidays': 0,
        }
        dict.update({
            '{}_days_periods'.format(i[1]): 0 for i in times_borders  # days periods counts
        })
        dict.update({
            i[0]: 0 for i in WorkerDay.TYPES  # days types
        })
        return dict

    if times_borders is None:
        times_borders = [
            [time(10), 'm'],
            [time(12), 'd'],
            [time(17), 'e'],
            [time(23, 59), 'n'],
        ]

    # t = check_time()
    ids = {u.id: u for u in employments}
    prod_days_list = list(ProductionDay.objects.filter(dt__gte=dt_start, dt__lte=dt_end, region_id=shop.region_id).order_by('dt'))

    shop_ids = list(set(user.shop_id for user in employments))
    shops = Shop.objects.filter(id__in=shop_ids)

    shops_triplets_dict = {}
    for shop in shops:
        break_triplets = shop.break_triplets
        list_of_break_triplets = json.loads(break_triplets)
        list_of_break_triplets = [[triplet[0], triplet[1], sum(triplet[2])] for triplet in list_of_break_triplets]
        shops_triplets_dict[shop.id] = list_of_break_triplets


    total_norm = get_norm_work_periods(prod_days_list, dt_start, dt_end)

    wdds = WorkerDay.objects.filter(
        Q(workerdaycashboxdetails__status__in=WorkerDayCashboxDetails.WORK_TYPES_LIST) | Q(workerdaycashboxdetails=None), # for doing left join
        dt__gte=dt_start,
        dt__lte=dt_end,
        employment_id__in=ids.keys(),
        child__isnull=True,
    ).values(
        'id',
        'worker_id',
        'employment_id',
        'shop_id',
        'dt',
        'type',
        'dttm_work_start',
        'dttm_work_end',
        'workerdaycashboxdetails__dttm_from',
        'workerdaycashboxdetails__dttm_to',
    ).order_by(
        'worker_id',
        'dt',
        'workerdaycashboxdetails__dttm_from',
    )

    workers_info = {}
    worker = {}
    worker_id = 0
    dt = None

    # t = check_time(t)
    for row in wdds:
        if worker_id != row['worker_id']:
            workers_info[worker_id] = worker
            worker_id = row['worker_id']

            employment = ids[row['employment_id']]
            norm_days = total_norm
            if (employment.dt_hired and (employment.dt_hired > dt_start)) or \
               (employment.dt_fired and (employment.dt_fired < dt_end)):
                dt_u_st = employment.dt_hired if employment.dt_hired else dt_start
                dt_e_st = employment.dt_fired if employment.dt_fired else dt_end
                norm_days = get_norm_work_periods(prod_days_list, dt_u_st, dt_e_st)

            worker = init_values(times_borders, norm_days)

        if dt != row['dt']:
            dt = row['dt']

            worker[row['type']] += 1

            if row['type'] in WorkerDay.TYPES_PAID:
                worker['paid_days'] += 1
                if row['type'] != WorkerDay.TYPE_WORKDAY:
                    worker['paid_hours'] += ProductionDay.WORK_NORM_HOURS[ProductionDay.TYPE_WORK]
                else:
                    # todo: из расписания перерывы вычитать

                    i = 0
                    while (i < len(times_borders)) and (row['dttm_work_start'].time() > times_borders[i][0]):
                        i += 1
                    str_name = '{}_days_periods'.format(times_borders[i][1])
                    worker[str_name] += 1

                # todo: вообще бред полный написан, поправил чисто чтобы exception'ы не вылетали
                if dt.day - 1 < len(prod_days_list) and prod_days_list[dt.day - 1] == ProductionDay.TYPE_HOLIDAY:
                    worker['work_in_holidays'] += 1

    # t = check_time(t)
    workers_info[worker_id] = worker
    workers_info.pop(0)

    hours_stat = wd_stat_count(wdds, shop)
    for wd in hours_stat:
        if 'hours_fact' not in workers_info[wd['worker_id']]:
            workers_info[wd['worker_id']]['hours_fact'] = 0
            workers_info[wd['worker_id']]['paid_hours'] = 0

        workers_info[wd['worker_id']]['hours_fact'] += round(wd['hours_fact'] or 0)
        workers_info[wd['worker_id']]['paid_hours'] += round(wd['hours_plan'] or 0)

    for worker_id, worker in workers_info.items():
        worker['diff_norm_days'] = worker['paid_days'] - worker['diff_norm_days']
        worker['diff_norm_hours'] = worker['paid_hours'] - worker['diff_norm_hours']
    #
    # t = check_time(t)
    return workers_info


def count_normal_days(dt_start, dt_end, employments, shop):
    """
    Считает количество нормального количества рабочих дней и рабочих часов от dt_start до dt_end

    Args:
        dt_start(datetime.date): дата начала подсчета
        dt_end(datetime.date): дата конца подсчета
        employments(QuerySet): список пользователей для которых считать

    """

    year_days = ProductionDay.objects.filter(
        dt__gte=dt_start,
        dt__lt=dt_end,
        region_id=shop.region_id,
    )
    dts_start_count = list(set([dt_start] + [u.dt_hired for u in employments if u.dt_hired and (u.dt_hired > dt_start)]))
    dts_start_count.sort()
    ind = len(dts_start_count) - 1
    ind_dt = len(year_days) - 1

    sum_days = 0
    sum_hours = 0
    dts_start_count_dict = {}
    while ind_dt >= 0:
        day = year_days[ind_dt]
        if day.type in ProductionDay.WORK_TYPES:
            if day.dt < dts_start_count[ind]:
                dts_start_count_dict[dts_start_count[ind]] = [sum_days, sum_hours]
                ind -= 1
            sum_days += 1
            sum_hours += ProductionDay.WORK_NORM_HOURS[day.type]
        ind_dt -= 1
    dts_start_count_dict[dts_start_count[ind]] = [sum_days, sum_hours]
    return dts_start_count_dict, year_days


def count_difference_of_normal_days(dt_end, employments, dt_start=None, shop=None):
    """
    Функция для подсчета разница между нормальным количеством отработанных дней и часов и фактическими

    Args:
        dt_start(datetime.date):
        dt_end(datetime.date):
        employments(QuerySet):

    Returns:
        (dict): словарь с id'шниками пользователей -- по ключам, и 'diff_prev_paid_days' и 'diff_prev_paid_hours' \
        -- по значениям
    """

    dt_start = dt_start if dt_start else dt.date(dt_end.year, 1, 1)
    dts_start_count_dict, _ = count_normal_days(dt_start, dt_end, employments, shop)

    usrs_ids = [u.id for u in employments]

    prev_info = list(Employment.objects.filter(
        Q(workerday__dt__gte=dt_start,
          workerday__dt__lt=dt_end) |
        Q(workerday=None), # for doing left join
        id__in=usrs_ids,
    ).values('id').annotate(
        count_workdays=Coalesce(Count('workerday', filter=Q(workerday__type__in=WorkerDay.TYPES_PAID)), 0),
        count_hours=Coalesce(Sum('workerday__work_hours', filter=Q(workerday__type__in=WorkerDay.TYPES_PAID)), 0),
    ).order_by('id'))
    prev_info = {user['id']: user for user in prev_info}
    employment_stat_dict = {}

    for u_it in range(len(employments)):
        dt_u_st = employments[u_it].dt_hired if employments[u_it].dt_hired and (employments[u_it].dt_hired > dt_start) else dt_start
        total_norm_days, total_norm_hours = dts_start_count_dict[dt_u_st]
        diff_prev_days = prev_info[employments[u_it].id]['count_workdays'] - total_norm_days if prev_info.get(
            employments[u_it].id, None) else 0 - total_norm_days
        diff_prev_hours = prev_info[employments[u_it].id]['count_hours'] - total_norm_hours if prev_info.get(
            employments[u_it].id, None) else 0 - total_norm_hours

        employment_stat_dict[employments[u_it].id] = {
            'diff_prev_paid_days': diff_prev_days,
            'diff_prev_paid_hours': diff_prev_hours
        }

    return employment_stat_dict
