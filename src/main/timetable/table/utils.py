from django.db.models import Q
from src.db.models import (
    WorkerDay,
    ProductionDay,
)
from datetime import time


import time as time2
def check_time(t=None):
    t2 = time2.time()
    if t:
        print(t2 - t)
    return t2


def count_work_month_stats(dt_start, dt_end, users, times_borders=None):
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
             i.value: 0 for i in WorkerDay.Type  # days types
        })
        return dict

    if times_borders is None:
        times_borders = [
            [time(10), 'm'],
            [time(12), 'd'],
            [time(17), 'e'],
            [time(23, 59), 'n'],
        ]

    t = check_time()
    users_ids = {u.id: u for u in users}
    prod_days_list = list(ProductionDay.objects.filter(dt__gte=dt_start, dt__lte=dt_end).order_by('dt'))

    total_norm = get_norm_work_periods(prod_days_list, dt_start, dt_end)

    wdds = list(WorkerDay.objects.filter(
        Q(workerdaycashboxdetails__is_break=False) | Q(workerdaycashboxdetails=None), # for doing left join
        dt__gte=dt_start,
        dt__lte=dt_end,
        worker_id__in=users_ids.keys(),
    ).values(
        'id',
        'worker_id',
        'dt',
        'type',
        'tm_work_start',
        'tm_work_end',
        'workerdaycashboxdetails__tm_from',
        'workerdaycashboxdetails__tm_to',
    ).order_by(
        'worker_id',
        'dt',
        'workerdaycashboxdetails__tm_from',
    ))

    workers_info = {}
    worker = {}
    worker_id = 0
    dt = None

    t = check_time(t)
    for row in wdds:
        if worker_id != row['worker_id']:
            workers_info[worker_id] = worker
            worker_id = row['worker_id']

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

            worker[row['type']] += 1

            if row['type'] in WorkerDay.TYPES_PAID:
                worker['paid_days'] += 1
                if row['type'] != WorkerDay.Type.TYPE_WORKDAY.value:
                    worker['paid_hours'] += ProductionDay.WORK_NORM_HOURS[ProductionDay.TYPE_WORK]
                else:
                    i = 0
                    while (i < len(times_borders)) and (row['tm_work_start'] > times_borders[i][0]):
                        i += 1
                    str_name = '{}_days_periods'.format(times_borders[i][1])
                    worker[str_name] += 1

                if prod_days_list[dt.day - 1] == ProductionDay.TYPE_HOLIDAY:
                    worker['work_in_holidays'] += 1

        if row['workerdaycashboxdetails__tm_from']:
            worker['paid_hours'] += timediff(
                row['workerdaycashboxdetails__tm_from'],
                row['workerdaycashboxdetails__tm_to'],
            )

    t = check_time(t)
    workers_info[worker_id] = worker
    workers_info.pop(0)
    for key, worker in workers_info.items():
        workers_info[key]['diff_norm_days'] = worker['paid_days'] - worker['diff_norm_days']
        workers_info[key]['diff_norm_hours'] = worker['paid_hours'] - worker['diff_norm_hours']

    for worker_id in users_ids.keys():
        if worker_id not in workers_info.keys():
            workers_info[worker_id] = init_values(times_borders, total_norm)
    t = check_time(t)
    return workers_info


def count_normal_days(dt_start, dt_end, usrs):
    """
    count normal amount of working days and working hours from dt_start to dt_end
    :param dt_end:
    :param dt_start:
    :param usrs:
    :return:
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


def timediff(tm_s, tm_e):
    diff = (tm_e.hour - tm_s.hour) + (tm_e.minute - tm_s.minute) / 60
    if diff < 0:
        diff += 24
    return diff