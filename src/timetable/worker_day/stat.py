from src.base.models import Shop, ProductionDay
from src.main.timetable.table.utils import  count_difference_of_normal_days
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails


from datetime import time, timedelta
import datetime
from django.db.models import Sum, Q, Count
from django.db.models.functions import Coalesce

from src.main.urv.utils import wd_stat_count
from django.db.models.functions import Extract, Coalesce, Cast, Ceil
import pandas

def count_month_stat(filterset, employments):
    if filterset.form.is_valid():
        data = filterset.form.cleaned_data

    shop_id =data['shop_id']
    dt_start = data['dt_from']
    dt_end = data['dt_to']
    dt_year_start = datetime.date(data['dt_from'].year,1,1)
    shop = Shop.objects.get(id=shop_id)

    cal = CalendarPaidDays(dt_year_start, dt_end, shop.region_id)
    employment_dict = {e.id: e for e in employments}

    worker_days = WorkerDay.objects.filter(
        dt__gte=dt_year_start,
        dt__lte=dt_end,
        employment_id__in=employments,
    ).order_by(
        'worker_id',
        'dt',
        'is_approved',
        'is_fact'
    )

    month_info = {}
    worker_stat = {}
    worker_id = 0

    for worker_day in worker_days:
        if worker_id != worker_day.worker_id:
            if worker_id:
                for app in ['approved', 'not_approved']:
                    for period in ['days', 'hours']:
                        worker_stat['plan'][app]['overtime'][period] += worker_stat['plan'][app][period]['total']
                        worker_stat['plan'][app]['overtime_prev'][period] += worker_stat['plan'][app]['prev'][period]['total']
                    worker_stat['plan'][app].pop('prev')

                month_info[worker_id] = worker_stat
            worker_id = worker_day.worker_id

            employment = employment_dict[worker_day.employment_id]
            paid_days_n_hours = cal.paid_days(dt_start, dt_end, employment)
            paid_days_n_hours_prev = cal.paid_days(dt_year_start, dt_start, employment)

            worker_stat = init_values()
            worker_stat['plan']['approved']['overtime'] = paid_days_n_hours
            worker_stat['plan']['not_approved']['overtime'] = paid_days_n_hours
            worker_stat['plan']['approved']['overtime_prev'] = paid_days_n_hours_prev
            worker_stat['plan']['not_approved']['overtime_prev'] = paid_days_n_hours_prev

        plan_or_fact = 'fact' if worker_day.is_fact else 'plan'
        approved = 'approved' if worker_day.is_approved else 'not_approved'
        cur_stat = worker_stat[plan_or_fact][approved]
        #previous period
        if worker_day.dt < dt_start:
            if worker_day.is_fact:
                continue
            cur_stat = cur_stat['prev']
        else:
            cur_stat['day_type'][worker_day.type] += 1

        if worker_day.type in WorkerDay.TYPES_PAID:
            field = 'shop' if worker_day.shop_id == shop.id else 'other'
            for f in [field, 'total']:
                cur_stat['days'][f] += 1
                cur_stat['hours'][f] += ProductionDay.WORK_NORM_HOURS[ProductionDay.TYPE_WORK]


    month_info[worker_id] = worker_stat


    # stat_prev_month = count_difference_of_normal_days(dt_end=dt_start, employments=employments, shop=shop)
    #
    # for employment in employments:
    #     if employment.user_id not in month_info:
    #         continue
    #     emp_prev_stat = stat_prev_month[employment.id]
    #     emp_month_info = month_info[employment.user_id]
    #
    #     emp_month_info.update({
    #         'overtime_days_prev': emp_prev_stat['diff_prev_paid_days'],
    #         'overtime_hours_prev': emp_prev_stat['diff_prev_paid_hours'],
    #         'diff_total_paid_days': emp_prev_stat['diff_prev_paid_days'] + emp_month_info['diff_norm_days'],
    #         'diff_total_paid_hours': emp_prev_stat['diff_prev_paid_hours'] + emp_month_info['diff_norm_hours'],
    #     })
    return month_info


def init_values():
    dict = {
        'plan': {
            'approved': {
                'days': {'total': 0, 'shop': 0, 'other': 0},
                'hours': {'total': 0, 'shop': 0, 'other': 0},
                'overtime': {'days': 0, 'hours': 0},
                'day_type': {i[0]: 0 for i in WorkerDay.TYPES},
                'prev': {
                    'days': {'total': 0, 'shop': 0, 'other': 0},
                    'hours': {'total': 0, 'shop': 0, 'other': 0},
                },
            },
            'not_approved': {
                'days': {'total': 0, 'shop': 0, 'other': 0},
                'hours': {'total': 0, 'shop': 0, 'other': 0},
                'overtime': {'days': 0, 'hours': 0},
                'day_type': {i[0]: 0 for i in WorkerDay.TYPES},
                'prev': {
                    'days': {'total': 0, 'shop': 0, 'other': 0},
                    'hours': {'total': 0, 'shop': 0, 'other': 0},
                },
            }
        },
        'fact': {
            'approved': {
                'hours': {'total': 0, 'shop': 0, 'other': 0},
                'days': {'total': 0, 'shop': 0, 'other': 0},
            },
            'not_approved': {
                'hours': {'total': 0, 'shop': 0, 'other': 0},
                'days': {'total': 0, 'shop': 0, 'other': 0},
            },
        },
        # 'day_type':{i[0]: 0 for i in WorkerDay.TYPES}
    }
    return dict


class CalendarPaidDays:
    def __init__(self,dt_start, dt_end, region_id):
        prod_days_list = list(ProductionDay.objects.filter(
            dt__gte=dt_start,
            dt__lte=dt_end,
            region_id=region_id,
            type__in=ProductionDay.WORK_TYPES
        ).values_list('dt', 'type'))

        df = pandas.DataFrame(prod_days_list, columns=['dt', 'type'])
        df.set_index('dt', inplace=True)
        df['hours'] = df['type'].apply(lambda x: ProductionDay.WORK_NORM_HOURS[x])
        self.calendar_days = df

    def paid_days(self, dt_start, dt_end, employment = None):
        if employment.dt_hired and employment.dt_hired >= dt_start:
            dt_start = employment.dt_hired
        if employment.dt_fired and employment.dt_fired <= dt_end:
            dt_end = employment.dt_fired

        day_hours = self.calendar_days.loc[(
            (self.calendar_days.index >= dt_start)
            & (self.calendar_days.index <= dt_end)
        )].hours

        return {
            'days': -day_hours.count(),
            'hours': -day_hours.sum(),
        }


