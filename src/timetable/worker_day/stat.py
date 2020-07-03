from datetime import timedelta, date
from copy import deepcopy
import pandas

from django.db.models import (
    Count, Sum,
    Exists, OuterRef, Subquery,
    F, Q,
    Case, When, Value,
    BooleanField, FloatField)
from django.db.models.functions import Extract, Cast, Coalesce, TruncDate

from src.base.models import Employment, Shop, ProductionDay
from src.forecast.models import PeriodClients
from src.timetable.models import WorkerDay


def count_daily_stat(shop_id, data):
    def daily_stat_tmpl():
        day = {"shifts": 0, "paid_hours": 0, "fot": 0.0}
        ap_na = {
            "shop": deepcopy(day),
            "outsource": deepcopy(day),
            "vacancies": deepcopy(day)
        }
        plan_fact = {
            "approved": deepcopy(ap_na),
            "not_approved": deepcopy(ap_na),
            "combined": deepcopy(ap_na)
        }
        return {
            'plan': deepcopy(plan_fact),
            'fact': deepcopy(plan_fact),
        }
    dt_start = data['dt_from']
    dt_end = data['dt_to']

    emp_subq_shop = Employment.objects.filter(
        Q(dt_fired__gte=OuterRef('dt')) | Q(dt_fired__isnull=True),
        user_id = OuterRef('worker_id'),
        shop_id=shop_id,
        dt_hired__lte = OuterRef('dt'))

    emp_subq = Employment.objects.filter(
        Q(dt_fired__gte=OuterRef('dt')) | Q(dt_fired__isnull=True),
        user_id = OuterRef('worker_id'),
        dt_hired__lte = OuterRef('dt')
    ).exclude(
        shop_id=shop_id
    )

    plan_approved_subq = WorkerDay.objects.filter(
        dt=OuterRef('dt'),
        is_fact=False,
        is_approved=True,
        worker_id = OuterRef('worker_id'),
        type=WorkerDay.TYPE_WORKDAY,
    )

    not_approved_subq = WorkerDay.objects.filter(
        dt=OuterRef('dt'),
        is_fact=OuterRef('is_fact'),
        is_approved=False,
        worker_id = OuterRef('worker_id'),
    )
    cond = Q()
    if 'worker_id__in' in data and data['worker_id__in'] is not None:
        cond = Q(worker_id__in=data['worker_id__in'])

    worker_days = WorkerDay.objects.filter(
        cond,
        dt__gte=dt_start,
        dt__lte=dt_end,
        shop_id=shop_id,
        type=WorkerDay.TYPE_WORKDAY,
        worker_id__isnull=False,
    ).annotate(
        salary=Coalesce(Subquery(emp_subq_shop.values('salary')[:1]), Subquery(emp_subq.values('salary')[:1]), 0),
        is_shop=Exists(emp_subq_shop),
        has_plan=Exists(plan_approved_subq),
    ).filter(
        Q(is_fact=False)|Q(has_plan=True)
    )

    worker_days_stat = worker_days.values(
        'dt', 'is_fact', 'is_approved', 'is_shop'
    ).annotate(
        shifts=Count('dt'),
        paid_hours=Sum(Extract(F('work_hours'), 'epoch') / 3600),
        fot=Sum(Cast(Extract(F('work_hours'), 'epoch') / 3600 * F('salary'), FloatField()))
    )

    stat = {}
    for day in worker_days_stat:
        dt = str(day.pop('dt'))
        if dt not in stat:
            stat[dt] = daily_stat_tmpl()
        plan_or_fact = 'fact' if day.pop('is_fact') else 'plan'
        approved = 'approved' if day.pop('is_approved') else 'not_approved'
        shop = 'shop' if day.pop('is_shop') else 'outsource'

        stat[dt][plan_or_fact][approved][shop] = day

    worker_days_combined = worker_days.annotate(
        has_na_child=Exists(not_approved_subq)).filter(
        Q(is_approved=False) | Q(has_na_child=False)
    ).values(
        'dt', 'is_fact', 'is_shop'
    ).annotate(
        shifts=Count('dt'),
        paid_hours=Sum(Extract(F('work_hours'), 'epoch') / 3600),
        fot=Sum(Cast(Extract(F('work_hours'), 'epoch') / 3600 * F('salary'), FloatField()))
    )
    for day in worker_days_combined:
        dt = str(day.pop('dt'))
        if dt not in stat:
            stat[dt] = daily_stat_tmpl()
        plan_or_fact = 'fact' if day.pop('is_fact') else 'plan'
        shop = 'shop' if day.pop('is_shop') else 'outsource'

        stat[dt][plan_or_fact]['combined'][shop] = day

    #Открытые вакансии
    worker_days = WorkerDay.objects.filter(
        dt__gte=dt_start,
        dt__lte=dt_end,
        shop_id=shop_id,
        type=WorkerDay.TYPE_WORKDAY,
        is_vacancy=True,
        worker_id__isnull=True,
    ).values(
        'dt',
        'is_approved'
    ).annotate(
        shifts=Count('dt'),
        paid_hours = Sum(Extract(F('work_hours'), 'epoch') / 3600),
    )

    for day in worker_days:
        approved = 'approved' if day.pop('is_approved') else 'not_approved'
        dt = str(day.pop('dt'))
        if dt not in stat:
            stat[dt] = daily_stat_tmpl()
        stat[dt]['plan'][approved]['vacancies'] = day

    q = [# (metric_name, field_name, Q)
        ('work_types', 'operation_type__work_type_id', Q(operation_type__work_type__shop_id=shop_id)),
        ('operation_types', 'operation_type_id', Q(operation_type__operation_type_name__is_special=True)),
    ]

    for (metric_name, field_name, cond) in q:
        period_clients = PeriodClients.objects.filter(
            cond,
            dttm_forecast__gte=dt_start,
            dttm_forecast__lte=dt_end,
        ).annotate(
            dt=TruncDate('dttm_forecast'),
            field=F(field_name)
        ).values('dt','field'
        ).annotate(value=Sum('value'))

        for day in period_clients:
            dt = str(day.pop('dt'))
            if dt not in stat:
                stat[dt] = daily_stat_tmpl()
            if metric_name not in stat[dt]:
                stat[dt][metric_name] = {
                }
            stat[dt][metric_name][day['field']]=day['value']
    return stat


def count_worker_stat(shop_id, data):
    dt_start = data['dt_from']
    dt_end = data['dt_to']
    worker_ids = data['worker_id__in']
    dt_year_start = date(data['dt_from'].year,1,1)
    shop = Shop.objects.get(id=shop_id)

    cal = CalendarPaidDays(dt_year_start, dt_end, shop.region_id)

    employments = Employment.objects.get_active(
        network_id=shop.network_id,
        dt_from=dt_year_start,
        dt_to=dt_end,
        shop_id=shop_id)
    if worker_ids:
        employments = employments.filter(user_id__in=worker_ids)

    worker_dict = {e.user_id: e for e in employments}

    worker_days = WorkerDay.objects.filter(
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
        'plan': {'approved': None, 'not_approved': None},
        'fact': {'approved': None, 'not_approved': None}
    }
    dt = worker_days[0].dt

    for worker_day in worker_days:
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
            if worker_day.dt >= dt_start and not worker_day.is_fact and (worker_day.shop_id is None or worker_day.shop_id == shop_id):
                cur_stat['day_type'][worker_day.type] += 1

            if worker_day.type in WorkerDay.TYPES_PAID:
                fields = ['overtime_prev']
                if worker_day.dt >= dt_start:
                    if worker_day.shop_id == shop.id or worker_day.type == WorkerDay.TYPE_BUSINESS_TRIP:
                        field = 'shop'
                    else:
                        field = 'other'
                    fields = [field, 'total', 'overtime']
                days, hours = count_fact(worker_day, wdays)
                for f in fields:
                    cur_stat['paid_days'][f] += days
                    cur_stat['paid_hours'][f] += hours

    if worker_id:
        month_info[worker_id] = worker_stat

    return month_info


def count_fact(fact, wdays):
    if not fact.is_fact:
        return (1, fact.work_hours.seconds / 3600)

    plan = wdays['plan']['approved'] if wdays['plan']['approved'] else None

    if not plan or plan.type != WorkerDay.TYPE_WORKDAY:
        return (0, 0)
    start = fact.dttm_work_start if fact.dttm_work_start > plan.dttm_work_start else plan.dttm_work_start
    end = fact.dttm_work_end if fact.dttm_work_end < plan.dttm_work_end else plan.dttm_work_end
    if end < start:
        return (0, 0)

    return (1, round((end-start).seconds / 3600))


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

