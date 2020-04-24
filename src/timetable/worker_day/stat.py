from copy import deepcopy
from src.base.models import Shop, ProductionDay
from src.main.timetable.table.utils import  count_difference_of_normal_days
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails


from datetime import time, timedelta
import datetime
from src.base.models import Employment
from django.db.models import Sum, Q, Count
from django.db.models.functions import Coalesce

from src.main.urv.utils import wd_stat_count
from django.db.models.functions import Extract, Coalesce, Cast, Ceil
import pandas


def count_worker_stat(shop_id, data):

    # employments = self.filter_queryset(
    #     self.get_queryset()
    # )
    # shop_id =data['shop_id']
    dt_start = data['dt_from']
    dt_end = data['dt_to']
    worker_ids = data['worker_id__in']
    dt_year_start = datetime.date(data['dt_from'].year,1,1)
    shop = Shop.objects.get(id=shop_id)

    cal = CalendarPaidDays(dt_year_start, dt_end, shop.region_id)

    employments=Employment.objects.get_active(dt_year_start,dt_end, shop_id=shop_id)
    if worker_ids:
        employments=employments.filter(user_id__in=worker_ids)
    worker_dict = {e.user_id: e for e in employments}

    worker_days = WorkerDay.objects.filter(
        # Q(shop_id=shop_id)|Q(shop_id__isnull=True),
        dt__gte=dt_year_start,
        dt__lte=dt_end,
        worker_id__in=worker_dict.keys()
    )
    worker_days = worker_days.order_by(
        'worker_id',
        'dt',
        'is_fact',
        'is_approved',
    )
    if not len(worker_days):
        return {}

    month_info = {}
    worker_stat = {}
    worker_id = 0
    wdays = {
        'plan': {'approved':None,'not_approved':None},
        'fact': {'approved': None, 'not_approved': None}
    }
    dt = worker_days[0].dt

    for i, worker_day in enumerate(worker_days):
        if worker_id != worker_day.worker_id or dt != worker_day.dt:
            dt = worker_day.dt
            wdays = {
                'plan': {'approved': None, 'not_approved': None},
                'fact': {'approved': None, 'not_approved': None}
            }
        if worker_id != worker_day.worker_id:
            if worker_id:
                month_info[worker_id] = worker_stat
            worker_id = worker_day.worker_id

            employment = worker_dict[worker_day.worker_id]
            paid_days_n_hours = cal.paid_days(dt_start, dt_end, employment)
            paid_days_n_hours_prev = cal.paid_days(dt_year_start, dt_start-timedelta(days=1), employment)

            worker_stat = init_values(paid_days_n_hours,paid_days_n_hours_prev)

        plan_or_fact = 'fact' if worker_day.is_fact else 'plan'
        approved = ['approved'] if worker_day.is_approved else ['not_approved', 'combined']

        wdays[plan_or_fact][approved[0]] = worker_day

        # approved must come later then not approved
        if worker_day.is_approved and not wdays[plan_or_fact]['not_approved']:
            approved.append('combined')

        for app in approved:
            cur_stat = worker_stat[plan_or_fact][app]

            if worker_day.dt >= dt_start and not worker_day.is_fact:
                cur_stat['day_type'][worker_day.type] += 1

            if worker_day.type in WorkerDay.TYPES_PAID:
                fields = ['overtime_prev']
                if worker_day.dt >= dt_start:
                    field = 'shop' if worker_day.shop_id == shop.id else 'other'
                    fields = [field, 'total', 'overtime']
                for f in fields:
                    cur_stat['paid_days'][f] += 1
                    cur_stat['paid_hours'][f] += count_fact(worker_day, wdays)

    if worker_id:
        month_info[worker_id] = worker_stat

    return month_info


def count_fact(fact, wdays):
    if not fact.is_fact:
        return fact.work_hours.seconds/3600

    plan = wdays['plan']['approved'] if wdays['plan']['approved'] else None

    if not plan or plan.type != WorkerDay.TYPE_WORKDAY:
        return 0
    start = fact.dttm_work_start if fact.dttm_work_start > plan.dttm_work_start else plan.dttm_work_start
    end = fact.dttm_work_end if fact.dttm_work_end < plan.dttm_work_end else plan.dttm_work_end
    if end < start:
        return 0

    return round((end-start).seconds / 3600)


def init_values(overtime, overtime_prev):
    days = {'total': 0, 'shop': 0, 'other': 0, 'overtime': overtime['days'],
            'overtime_prev': overtime_prev['days']}
    hours = {'total': 0, 'shop': 0, 'other': 0, 'overtime': overtime['hours'],
            'overtime_prev': overtime_prev['hours']}
    approved = {
        'paid_days': days.copy(),
        'paid_hours': hours.copy(),
    }

    dict = {
        'fact': {
            'approved': deepcopy(approved),
            'not_approved': deepcopy(approved),
            'combined': deepcopy(approved)
        }}
    approved['day_type'] = {i: 0 for i in WorkerDay.TYPES_USED}

    dict['plan'] = {
        'approved': deepcopy(approved),
        'not_approved': deepcopy(approved),
        'combined': deepcopy(approved)
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


