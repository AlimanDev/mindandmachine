from src.db.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    ProductionDay,
    User,
    Shop,
)
import json
from datetime import time
from ..utils import timediff
import datetime as dt
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce

from src.util.models_converter import WorkerDayConverter


def count_work_month_stats(dt_start, dt_end, users, times_borders=None):
    """
    Функция для посчета статистики работника за месяц

    Args:
         dt_start(datetime.date): дата начала подсчета
         dt_end(datetime.date): дата конца подсчета
         users(QuerySet): список пользователей для которых считать
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
            WorkerDayConverter.convert_type(i.value): 0 for i in WorkerDay.Type  # days types
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
    users_ids = {u.id: u for u in users}
    prod_days_list = list(ProductionDay.objects.filter(dt__gte=dt_start, dt__lte=dt_end).order_by('dt'))

    shop_ids = list(set(user.shop_id for user in users))
    shops = Shop.objects.filter(id__in=shop_ids)

    shops_triplets_dict = {}
    for shop in shops:
        break_triplets = shop.break_triplets
        list_of_break_triplets = json.loads(break_triplets)
        list_of_break_triplets = [[triplet[0], triplet[1], sum(triplet[2])] for triplet in list_of_break_triplets]
        shops_triplets_dict[shop.id] = list_of_break_triplets


    total_norm = get_norm_work_periods(prod_days_list, dt_start, dt_end)

    wdds = list(WorkerDay.objects.filter(
        Q(workerdaycashboxdetails__status__in=WorkerDayCashboxDetails.WORK_TYPES_LIST) | Q(workerdaycashboxdetails=None), # for doing left join
        dt__gte=dt_start,
        dt__lte=dt_end,
        employment_id__in=users_ids.keys(),
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
    ))

    workers_info = {}
    worker = {}
    worker_id = 0
    dt = None

    # t = check_time(t)
    for row in wdds:
        if worker_id != row['employment_id']:
            workers_info[worker_id] = worker
            worker_id = row['employment_id']

            user = users_ids[worker_id]
            norm_days = total_norm
            if (user.dt_hired and (user.dt_hired > dt_start)) or \
               (user.dt_fired and (user.dt_fired < dt_end)):
                dt_u_st = user.dt_hired if user.dt_hired else dt_start
                dt_e_st = user.dt_fired if user.dt_fired else dt_end
                norm_days = get_norm_work_periods(prod_days_list, dt_u_st, dt_e_st)

            worker = init_values(times_borders, norm_days)

        if dt != row['dt']:
            dt = row['dt']

            worker[WorkerDayConverter.convert_type(row['type'])] += 1

            if row['type'] in WorkerDay.TYPES_PAID:
                worker['paid_days'] += 1
                if row['type'] != WorkerDay.Type.TYPE_WORKDAY.value:
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

        if row['workerdaycashboxdetails__dttm_from'] and row['workerdaycashboxdetails__dttm_to']:
            duration_of_workerday = round(timediff(
                row['workerdaycashboxdetails__dttm_from'],
                row['workerdaycashboxdetails__dttm_to'],
            ))

            list_of_break_triplets = shops_triplets_dict[user.shop_id]
            time_break_triplets = 0
            for triplet in list_of_break_triplets:
                if float(triplet[0]) < duration_of_workerday * 60 <= float(triplet[1]):
                    time_break_triplets = triplet[2]
            duration_of_workerday -= round(time_break_triplets / 60, 3)
            worker['paid_hours'] += duration_of_workerday

    # t = check_time(t)
    workers_info[worker_id] = worker
    workers_info.pop(0)
    for key, worker in workers_info.items():
        workers_info[key]['diff_norm_days'] = worker['paid_days'] - worker['diff_norm_days']
        workers_info[key]['diff_norm_hours'] = worker['paid_hours'] - worker['diff_norm_hours']

    for worker_id in users_ids.keys():
        if worker_id not in workers_info.keys():
            workers_info[worker_id] = init_values(times_borders, total_norm)
    # t = check_time(t)
    return workers_info


def count_normal_days(dt_start, dt_end, usrs):
    """
    Считает количество нормального количества рабочих дней и рабочих часов от dt_start до dt_end

    Args:
        dt_start(datetime.date): дата начала подсчета
        dt_end(datetime.date): дата конца подсчета
        usrs(QuerySet): список пользователей для которых считать

    """

    year_days = ProductionDay.objects.filter(
        dt__gte=dt_start,
        dt__lt=dt_end,
    )
    dts_start_count = list(set([dt_start] + [u.dt_hired for u in usrs if u.dt_hired and (u.dt_hired > dt_start)]))
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


def count_difference_of_normal_days(dt_end, usrs, dt_start=None):
    """
    Функция для подсчета разница между нормальным количеством отработанных дней и часов и фактическими

    Args:
        dt_start(datetime.date):
        dt_end(datetime.date):
        usrs(QuerySet):

    Returns:
        (dict): словарь с id'шниками пользователей -- по ключам, и 'diff_prev_paid_days' и 'diff_prev_paid_hours' \
        -- по значениям
    """

    dt_start = dt_start if dt_start else dt.date(dt_end.year, 1, 1)
    dts_start_count_dict, _ = count_normal_days(dt_start, dt_end, usrs)

    usrs_ids = [u.id for u in usrs]

    prev_info = list(User.objects.filter(
        Q(workermonthstat__month__dt_first__gte=dt_start,
          workermonthstat__month__dt_first__lt=dt_end) |
        Q(workermonthstat=None), # for doing left join
        id__in=usrs_ids,
    ).values('id').annotate(
        count_workdays=Coalesce(Sum('workermonthstat__work_days'), 0),
        count_hours=Coalesce(Sum('workermonthstat__work_hours'), 0),
    ).order_by('id'))
    prev_info = {user['id']: user for user in prev_info}
    user_info_dict = {}

    for u_it in range(len(usrs)):
        dt_u_st = usrs[u_it].dt_hired if usrs[u_it].dt_hired and (usrs[u_it].dt_hired > dt_start) else dt_start
        total_norm_days, total_norm_hours = dts_start_count_dict[dt_u_st]
        diff_prev_days = prev_info[usrs[u_it].id]['count_workdays'] - total_norm_days if prev_info.get(
            usrs[u_it].id, None) else 0 - total_norm_days
        diff_prev_hours = prev_info[usrs[u_it].id]['count_hours'] - total_norm_hours if prev_info.get(
            usrs[u_it].id, None) else 0 - total_norm_hours

        user_info_dict[usrs[u_it].id] = {
            'diff_prev_paid_days': diff_prev_days,
            'diff_prev_paid_hours': diff_prev_hours
        }

    return user_info_dict
