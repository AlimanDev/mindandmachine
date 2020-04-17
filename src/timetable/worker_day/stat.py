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
    worker_dict = {e.user_id: e for e in employments}

    worker_days = WorkerDay.objects.filter(
        dt__gte=dt_year_start,
        dt__lte=dt_end,
        worker_id__in=worker_dict.keys(),
    ).order_by(
        'worker_id',
        'dt',
        'is_fact',
        'is_approved',
    )

    month_info = {}
    worker_stat = {}
    worker_id = 0
    wdays = {
        'plan': {'approved':None,'not_approved':None},
        'fact': {'approved': None, 'not_approved': None}
    }
    dt = worker_days[0].dt

    for i, worker_day in enumerate(worker_days):
        if worker_day.dt < dt_start and worker_day.is_fact:
            continue
        if worker_id != worker_day.worker_id or dt != worker_day.dt:
            dt = worker_day.dt
            wdays = {
                'plan': {'approved': None, 'not_approved': None},
                'fact': {'approved': None, 'not_approved': None}
            }
        if worker_id != worker_day.worker_id:
            if worker_id:
                for app in ['approved', 'not_approved']:
                    # for period in ['days', 'hours']:
                    #     worker_stat['plan'][app]['overtime'][period] += worker_stat['plan'][app][period]['total']
                    #     worker_stat['plan'][app]['overtime_prev'][period] += worker_stat['plan'][app]['prev'][period]['total']
                    worker_stat['plan'][app].pop('prev')

                month_info[worker_id] = worker_stat
            worker_id = worker_day.worker_id

            employment = worker_dict[worker_day.worker_id]
            paid_days_n_hours = cal.paid_days(dt_start, dt_end, employment)
            paid_days_n_hours_prev = cal.paid_days(dt_year_start, dt_start-timedelta(days=1), employment)

            worker_stat = init_values()
            worker_stat['plan']['approved']['overtime'] = paid_days_n_hours
            worker_stat['plan']['not_approved']['overtime'] = paid_days_n_hours.copy()
            worker_stat['plan']['approved']['overtime_prev'] = paid_days_n_hours_prev
            worker_stat['plan']['not_approved']['overtime_prev'] = paid_days_n_hours_prev.copy()


        plan_or_fact = 'fact' if worker_day.is_fact else 'plan'
        approved = ['approved'] if worker_day.is_approved else ['not_approved']

        wdays[plan_or_fact][approved[0]] = worker_day

        # approved must come later then not approved
        if worker_day.is_approved and not wdays[plan_or_fact]['not_approved']:
            approved.append('not_approved')

        for app in approved:
            cur_stat = worker_stat[plan_or_fact][app]

            #previous period
            if worker_day.dt < dt_start:
                cur_stat = cur_stat['prev']
            elif not worker_day.is_fact:
                cur_stat['day_type'][worker_day.type] += 1

            if worker_day.type in WorkerDay.TYPES_PAID:
                field = 'shop' if worker_day.shop_id == shop.id else 'other'
                for f in [field, 'total']:
                    cur_stat['days'][f] += 1
                    cur_stat['hours'][f] += count_fact(worker_day, wdays)

    if worker_id:
        for app in ['approved', 'not_approved']:
            for period in ['days', 'hours']:
                stat = worker_stat['plan'][app]
                stat['overtime'][period] += stat[period]['total']
                stat['overtime_prev'][period] += stat['prev'][period]['total']
            # worker_stat['plan'][app].pop('prev')

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


def count_fact(fact, wdays):
    if not fact.is_fact:
        return fact.work_hours.seconds/3600

    plan = wdays['plan']['approved'] if wdays['plan']['approved'] else wdays['plan']['not_approved']

    if not plan.type == WorkerDay.TYPE_WORKDAY:
        return 0
    start = fact.dttm_work_start if fact.dttm_work_start > plan.dttm_work_start else plan.dttm_work_start
    end = fact.dttm_work_end if fact.dttm_work_end < plan.dttm_work_end else plan.dttm_work_end
    if end < start:
        return 0

    return round((end-start).seconds / 3600)


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
        if employment:
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


