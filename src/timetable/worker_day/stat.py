from calendar import monthrange
from copy import deepcopy
from datetime import timedelta, datetime
from functools import lru_cache

import pandas as pd
from dateutil.relativedelta import relativedelta
from django.db.models import (
    Case, When, BooleanField, )
from django.db.models import (
    Count, Sum,
    Exists, OuterRef, Subquery,
    F, Q,
    Value,
    FloatField
)
from django.db.models.functions import Cast, TruncDate
from django.db.models.functions import Extract, Coalesce, Greatest, Least
from django.utils.functional import cached_property

from src.base.models import Employment, Shop, ProductionDay, SAWHSettingsMapping
from src.forecast.models import PeriodClients
from src.timetable.models import WorkerDay, ProdCal


def count_daily_stat(data):
    shop_id = data['shop_id']

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
        user_id=OuterRef('worker_id'),
        shop_id=shop_id,
        dt_hired__lte=OuterRef('dt'))

    emp_subq = Employment.objects.filter(
        Q(dt_fired__gte=OuterRef('dt')) | Q(dt_fired__isnull=True),
        user_id=OuterRef('worker_id'),
        dt_hired__lte=OuterRef('dt')
    ).exclude(
        shop_id=shop_id
    )

    plan_approved_subq = WorkerDay.objects.filter(
        dt=OuterRef('dt'),
        is_fact=False,
        is_approved=True,
        worker_id=OuterRef('worker_id'),
        type=WorkerDay.TYPE_WORKDAY,
    )

    not_approved_subq = WorkerDay.objects.filter(
        dt=OuterRef('dt'),
        is_fact=OuterRef('is_fact'),
        is_approved=False,
        parent_worker_day_id=OuterRef('id'),
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
        # worker_id__isnull=False,
    ).annotate(
        has_worker=Case(When(worker_id__isnull=True, then=Value(False)), default=Value(True),
                        output_field=BooleanField()),

        salary=Coalesce(Subquery(emp_subq_shop.values('salary')[:1]), Subquery(emp_subq.values('salary')[:1]), 0),
        is_shop=Exists(emp_subq_shop),
        has_plan=Exists(plan_approved_subq),
    ).filter(
        Q(is_fact=False) | Q(has_plan=True)
    )

    worker_days_stat = worker_days.values(
        'dt', 'is_fact', 'is_approved', 'is_shop', 'has_worker'
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
        is_shop = day.pop('is_shop')
        has_worker = day.pop('has_worker')
        shop = 'shop' if is_shop else \
            'outsource' if has_worker else \
                'vacancies'

        stat[dt][plan_or_fact][approved][shop] = day

    worker_days_combined = worker_days.annotate(
        has_na_child=Exists(not_approved_subq)).filter(
        Q(is_approved=False) | Q(has_na_child=False)
    ).values(
        'dt', 'is_fact', 'is_shop', 'has_worker'
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
        has_worker = day.pop('has_worker')
        is_shop = day.pop('is_shop')
        shop = 'shop' if is_shop else \
            'outsource' if has_worker else \
                'vacancies'

        stat[dt][plan_or_fact]['combined'][shop] = day

    q = [  # (metric_name, field_name, Q)
        ('work_types', 'operation_type__work_type_id', Q(operation_type__work_type__shop_id=shop_id)),
        ('operation_types', 'operation_type_id', Q(operation_type__operation_type_name__is_special=True)),
    ]
    shop = Shop.objects.get(pk=shop_id)
    for (metric_name, field_name, cond) in q:
        period_clients = PeriodClients.objects.filter(
            cond,
            dttm_forecast__date__gte=dt_start,
            dttm_forecast__date__lte=dt_end,
        ).annotate(
            dt=TruncDate('dttm_forecast'),
            field=F(field_name)
        ).values(
            'dt', 'field'
        ).annotate(value=Sum('value'))

        for day in period_clients:
            dt = str(day.pop('dt'))
            if dt not in stat:
                stat[dt] = daily_stat_tmpl()
            if metric_name not in stat[dt]:
                stat[dt][metric_name] = {
                }
            stat[dt][metric_name][day['field']] = day['value']
    return stat


class CalendarPaidDays:
    def __init__(self, dt_start, dt_end, region_id):
        prod_days_list = list(ProductionDay.objects.filter(
            dt__gte=dt_start,
            dt__lte=dt_end,
            region_id=region_id,
            type__in=ProductionDay.WORK_TYPES
        ).values_list('dt', 'type'))

        df = pd.DataFrame(prod_days_list, columns=['dt', 'type'])
        df.set_index('dt', inplace=True)
        df['hours'] = df['type'].apply(lambda x: ProductionDay.WORK_NORM_HOURS[x])
        self.calendar_days = df

    def paid_days(self, dt_start, dt_end, employment=None):
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

    def get_prod_cal_days(self, dt_start, dt_end, rate=100, hours_in_a_week=40):
        return self.calendar_days.loc[(
                (self.calendar_days.index >= dt_start)
                & (self.calendar_days.index <= dt_end)
        )].hours.sum() * (rate / 100) * (hours_in_a_week / 40)


@lru_cache(maxsize=24)
def get_month_range(year, month_num, return_days_in_month=False):
    month_start = datetime(year, month_num, 1).date()
    _weekday, days_in_month = monthrange(year, month_num)
    month_end = datetime(year, month_num, days_in_month).date()
    if return_days_in_month:
        return month_start, month_end, days_in_month
    return month_start, month_end


class WorkersStatsGetter:
    def __init__(self, shop_id, dt_from, dt_to, worker_id=None, worker_id__in=None):
        self.shop_id = shop_id
        self.dt_from = dt_from
        self.dt_to = dt_to
        self.worker_id = worker_id
        self.worker_id__in = worker_id__in
        self.year = dt_from.year
        self.month = dt_from.month

    @cached_property
    def workers_prod_cals(self):
        return ProdCal.get_workers_prod_cal_hours(
            user_ids=self.workers_dict.keys(),
            dt_from=self.acc_period_start,
            dt_to=self.acc_period_end,
        )

    @cached_property
    def shop(self):
        return Shop.objects.get(id=self.shop_id)

    @cached_property
    def network(self):
        return self.shop.network

    @cached_property
    def acc_period_range(self):
        return self.network.get_acc_period_range(self.dt_from)

    @cached_property
    def acc_period_start(self):
        acc_period_start, _end = self.acc_period_range
        return acc_period_start

    @cached_property
    def acc_period_end(self):
        _start, acc_period_end = self.acc_period_range
        return acc_period_end

    @cached_property
    def until_acc_period_end_range(self):
        dt_from = self.dt_from.replace(day=1)
        _acc_period_dt_from, acc_period_dt_to = self.acc_period_range
        return dt_from, acc_period_dt_to

    @cached_property
    def curr_month_range(self):
        dt_from = self.dt_from.replace(day=1)
        dt_to = self.dt_from.replace(day=monthrange(self.year, self.month)[1])
        return dt_from, dt_to

    @cached_property
    def curr_month_end_range(self):
        acc_period_dt_from, _acc_period_dt_to = self.acc_period_range
        dt_to = self.dt_from.replace(day=monthrange(self.year, self.month)[1])
        return acc_period_dt_from, dt_to

    @cached_property
    def prev_months_range(self):
        acc_period_dt_from, _acc_period_dt_to = self.acc_period_range
        dt_to = self.dt_from.replace(day=1) - timedelta(days=1)
        return acc_period_dt_from, dt_to

    @cached_property
    def prev_range(self):
        acc_period_dt_from, _acc_period_dt_to = self.acc_period_range
        prev_dt_to = self.dt_from - timedelta(days=1)
        return acc_period_dt_from, prev_dt_to

    @cached_property
    def employments_list(self):
        dt_from, dt_to = self.acc_period_range
        employments = Employment.objects.get_active(
            network_id=self.network.id,
            dt_from=dt_from,
            dt_to=dt_to,
            user__employments__shop_id=self.shop_id,
        ).select_related(
            'position'
        ).order_by(
            'dt_hired'
        ).extra(
            select={'sawh_hours_by_months': """SELECT V5."work_hours_by_months"
                 FROM "base_sawhsettingsmapping" V0
                          LEFT OUTER JOIN "base_sawhsettingsmapping_positions" V1
                                          ON (V0."id" = V1."sawhsettingsmapping_id")
                          LEFT OUTER JOIN "base_sawhsettingsmapping_shops" V3 ON (V0."id" = V3."sawhsettingsmapping_id")
                          INNER JOIN "base_sawhsettings" V5 ON (V0."sawh_settings_id" = V5."id")
                 WHERE ((V1."workerposition_id" = "base_employment"."position_id" OR
                         V3."shop_id" = "base_employment"."shop_id") AND
                        NOT (V0."id" IN (SELECT U1."sawhsettingsmapping_id"
                                         FROM "base_sawhsettingsmapping_exclude_positions" U1
                                         WHERE U1."workerposition_id" = "base_employment"."position_id")) AND
                        V0."year" = %s)
                 ORDER BY V0."priority" DESC
                 LIMIT 1"""},
            select_params=(self.year,),
        ).distinct()
        # в django 2 есть баг, при переходе на django 3 можно будет использовать следующий annotate
        # ).annotate(
        #     sawh_hours_by_months=Subquery(SAWHSettingsMapping.objects.filter(
        #         Q(positions__id=OuterRef('position_id')) | Q(shops__id=OuterRef('shop_id')),
        #         ~Q(exclude_positions__id=OuterRef('position_id')),
        #         year=self.year,
        #     ).order_by('-priority').values('sawh_settings__work_hours_by_months')[:1])
        # ).distinct()
        if self.worker_id:
            employments = employments.filter(user_id=self.worker_id)
        if self.worker_id__in:
            employments = employments.filter(user_id__in=self.worker_id__in)

        return list(employments)

    @cached_property
    def workers_dict(self):
        workers_dict = {}
        for e in self.employments_list:
            workers_dict.setdefault(e.user_id, []).append(e)
        return workers_dict

    def _get_is_fact_key(self, is_fact):
        return 'fact' if is_fact else 'plan'

    def _get_is_approved_key(self, is_approved):
        return 'approved' if is_approved else 'not_approved'

    def _get_selected_period_months(self):
        result = []

        current = self.dt_from
        until = self.dt_to

        while current <= until:
            result.append(current.month)
            current += relativedelta(months=1)
            current = current.replace(day=1)

        return result

    def run(self):
        res = {}
        acc_period_dt_from, acc_period_dt_to = self.acc_period_range
        selected_period_q = Q(dt__gte=self.dt_from, dt__lte=self.dt_to)
        prev_months_dt_from, prev_months_dt_to = self.prev_months_range
        prev_months_q = Q(dt__gte=prev_months_dt_from, dt__lte=prev_months_dt_to)
        curr_month_dt_from, curr_month_dt_to = self.curr_month_range
        curr_month_q = Q(dt__gte=curr_month_dt_from, dt__lte=curr_month_dt_to)
        curr_month_end_dt_from, curr_month_end_dt_to = self.curr_month_end_range
        curr_month_end_q = Q(dt__gte=curr_month_end_dt_from, dt__lte=curr_month_end_dt_to)
        until_acc_period_end_dt_from, until_acc_period_end_dt_to = self.until_acc_period_end_range
        until_acc_period_end_q = Q(dt__gte=until_acc_period_end_dt_from, dt__lte=until_acc_period_end_dt_to)

        selected_period_months = self._get_selected_period_months()
        curr_month = self.dt_from.month

        work_days = WorkerDay.objects.filter(
            dt__gte=acc_period_dt_from,
            dt__lte=acc_period_dt_to,
            worker_id__in=self.workers_dict.keys(),
        ).values(
            'worker_id',
            'is_fact',
            'is_approved',
        ).annotate(
            work_days_selected_shop=Coalesce(Count('id', filter=Q(selected_period_q, shop_id=self.shop_id,
                                                                  work_hours__gte=timedelta(0),
                                                                  type__in=WorkerDay.TYPES_WITH_TM_RANGE)), 0),
            work_days_other_shops=Coalesce(Count('id', filter=Q(selected_period_q, ~Q(shop_id=self.shop_id),
                                                                work_hours__gte=timedelta(0),
                                                                type__in=WorkerDay.TYPES_WITH_TM_RANGE)), 0),
            work_days_total=Coalesce(Count('id', filter=Q(selected_period_q, work_hours__gte=timedelta(0),
                                                          type__in=WorkerDay.TYPES_WITH_TM_RANGE)), 0),
            work_hours_selected_shop=Coalesce(Sum(Extract(F('work_hours'), 'epoch') / 3600,
                                                  filter=Q(selected_period_q, shop_id=self.shop_id,
                                                           work_hours__gte=timedelta(0),
                                                           type__in=WorkerDay.TYPES_WITH_TM_RANGE),
                                                  output_field=FloatField()), 0),
            work_hours_other_shops=Coalesce(Sum(Extract(F('work_hours'), 'epoch') / 3600,
                                                filter=Q(selected_period_q, ~Q(shop_id=self.shop_id),
                                                         work_hours__gte=timedelta(0),
                                                         type__in=WorkerDay.TYPES_WITH_TM_RANGE),
                                                output_field=FloatField()), 0),
            work_hours_total=Coalesce(Sum(Extract(F('work_hours'), 'epoch') / 3600,
                                          filter=Q(selected_period_q, work_hours__gte=timedelta(0),
                                                   type__in=WorkerDay.TYPES_WITH_TM_RANGE),
                                          output_field=FloatField()), 0),
            work_hours_acc_period=Coalesce(Sum(Extract(F('work_hours'), 'epoch') / 3600,
                                               filter=Q(work_hours__gte=timedelta(0),
                                                        type__in=WorkerDay.TYPES_WITH_TM_RANGE),
                                               output_field=FloatField()), 0),
            work_hours_prev_months=Coalesce(Sum(Extract(F('work_hours'), 'epoch') / 3600,
                                                filter=Q(prev_months_q, work_hours__gte=timedelta(0),
                                                         type__in=WorkerDay.TYPES_WITH_TM_RANGE),
                                                output_field=FloatField()), 0),
            work_hours_until_acc_period_end=Coalesce(Sum(Extract(F('work_hours'), 'epoch') / 3600,
                                                         filter=Q(until_acc_period_end_q, work_hours__gte=timedelta(0),
                                                                  type__in=WorkerDay.TYPES_WITH_TM_RANGE),
                                                         output_field=FloatField()), 0)
        ).order_by('worker_id', '-is_fact', '-is_approved')  # нужно для work_hours_prev_months
        for wd_dict in work_days:
            data = res.setdefault(
                wd_dict['worker_id'], {}
            ).setdefault(
                self._get_is_fact_key(wd_dict['is_fact']), {}
            ).setdefault(
                self._get_is_approved_key(wd_dict['is_approved']), {}
            )
            work_days = data.setdefault('work_days', {})
            work_days['selected_shop'] = wd_dict['work_days_selected_shop']
            work_days['other_shops'] = wd_dict['work_days_other_shops']
            work_days['total'] = wd_dict['work_days_total']

            work_hours = data.setdefault('work_hours', {})
            work_hours['selected_shop'] = wd_dict['work_hours_selected_shop']
            work_hours['other_shops'] = wd_dict['work_hours_other_shops']
            work_hours['total'] = wd_dict['work_hours_total']
            work_hours['acc_period'] = wd_dict['work_hours_acc_period']
            work_hours['until_acc_period_end'] = wd_dict['work_hours_until_acc_period_end']

            # за прошлые месяцы отработанные часы берем из факта подтвержденного
            if wd_dict['is_fact'] and wd_dict['is_approved']:
                work_hours['prev_months'] = wd_dict['work_hours_prev_months']
            else:
                work_hours['prev_months'] = res.get(
                    wd_dict['worker_id'], {}).get('fact', {}).get('approved', {}).get('work_hours', {}).get(
                    'prev_months', 0)

        work_days = WorkerDay.objects.filter(
            dt__gte=acc_period_dt_from,
            dt__lte=acc_period_dt_to,
            worker_id__in=self.workers_dict.keys(),
        ).values(
            'worker_id',
            'is_fact',
            'is_approved',
            'type',
        ).annotate(
            day_type_count=Count('type', filter=selected_period_q),
        )
        for wd_dict in work_days:
            data = res.setdefault(
                wd_dict['worker_id'], {}
            ).setdefault(
                self._get_is_fact_key(wd_dict['is_fact']), {}
            ).setdefault(
                self._get_is_approved_key(wd_dict['is_approved']), {}
            )
            day_type = data.setdefault('day_type', {})
            day_type[wd_dict['type']] = wd_dict['day_type_count']

        prod_cal_qs = ProdCal.objects.filter(
            dt__gte=acc_period_dt_from,
            dt__lte=acc_period_dt_to,
            user_id__in=self.workers_dict.keys(),
        ).values(
            'user_id',
            'employment_id',
            'dt__month',
        ).annotate(
            period_start=Greatest('employment__dt_hired', Value(acc_period_dt_from)),
            period_end=Least('employment__dt_fired', Value(acc_period_dt_to)),
            has_vacation_or_sick_plan_approved=Exists(WorkerDay.objects.filter(
                worker_id=OuterRef('user_id'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=True,
                type__in=WorkerDay.TYPES_REDUCING_NORM_HOURS,
            )),
            vacation_or_sick_plan_approved_count=Count(Subquery(WorkerDay.objects.filter(
                worker_id=OuterRef('user_id'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=True,
                type__in=WorkerDay.TYPES_REDUCING_NORM_HOURS,
            ).values('id'))),
            vacation_or_sick_plan_approved_count_selected_period=Count(Subquery(WorkerDay.objects.filter(
                selected_period_q,
                worker_id=OuterRef('user_id'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=True,
                type__in=WorkerDay.TYPES_REDUCING_NORM_HOURS,
            ).values('id'))),
            has_vacation_or_sick_plan_not_approved=Exists(WorkerDay.objects.filter(
                worker_id=OuterRef('user_id'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=False,
                type__in=WorkerDay.TYPES_REDUCING_NORM_HOURS,
            )),
            vacation_or_sick_plan_not_approved_count=Count(Subquery(WorkerDay.objects.filter(
                worker_id=OuterRef('user_id'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=False,
                type__in=WorkerDay.TYPES_REDUCING_NORM_HOURS,
            ).values('id'))),
            vacation_or_sick_plan_not_approved_count_selected_period=Count(Subquery(WorkerDay.objects.filter(
                selected_period_q,
                worker_id=OuterRef('user_id'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=False,
                type__in=WorkerDay.TYPES_REDUCING_NORM_HOURS,
            ).values('id'))),
            norm_hours_acc_period=Coalesce(
                Sum('norm_hours'), 0),
            norm_hours_prev_months=Coalesce(
                Sum('norm_hours', filter=prev_months_q), 0),
            norm_hours_curr_month=Coalesce(
                Sum('norm_hours', filter=curr_month_q), 0),
            norm_hours_curr_month_end=Coalesce(
                Sum('norm_hours', filter=curr_month_end_q), 0),
            empl_days_count=Count('dt'),
            empl_days_count_selected_period=Count('dt', filter=selected_period_q),
        )

        for pc_dict in prod_cal_qs:
            for is_fact_key in ['plan', 'fact']:
                for is_approved_key in ['approved', 'not_approved']:
                    data = res.setdefault(
                        pc_dict['user_id'], {}
                    ).setdefault(
                        is_fact_key, {}
                    ).setdefault(
                        is_approved_key, {}
                    )

                    norm_hours = data.setdefault('norm_hours', {})
                    empl_dict = res.setdefault(
                        pc_dict['user_id'], {}).setdefault('employments', {}).setdefault(pc_dict['employment_id'], {})
                    if is_fact_key == 'plan' and is_approved_key == 'not_approved':
                        if pc_dict['has_vacation_or_sick_plan_not_approved'] is False:
                            norm_hours['acc_period'] = norm_hours.get('acc_period', 0) + pc_dict[
                                'norm_hours_acc_period']
                            norm_hours['prev_months'] = norm_hours.get('prev_months', 0) + pc_dict[
                                'norm_hours_prev_months']
                            norm_hours['curr_month'] = norm_hours.get('curr_month', 0) + pc_dict[
                                'norm_hours_curr_month']
                            norm_hours['curr_month_end'] = norm_hours.get('curr_month_end', 0) + pc_dict[
                                'norm_hours_prev_months'] + pc_dict['norm_hours_curr_month']

                        empl_dict.setdefault('vacation_or_sick_plan_not_approved_count', {})[pc_dict['dt__month']] = \
                            norm_hours.get('vacation_or_sick_plan_not_approved_count', 0) + \
                            pc_dict['vacation_or_sick_plan_not_approved_count']
                        empl_dict.setdefault('vacation_or_sick_plan_not_approved_count_selected_period', {})[pc_dict['dt__month']] = \
                            norm_hours.get('vacation_or_sick_plan_not_approved_count_selected_period', 0) + \
                            pc_dict['vacation_or_sick_plan_not_approved_count_selected_period']
                    else:
                        if pc_dict['has_vacation_or_sick_plan_approved'] is False:
                            norm_hours['acc_period'] = norm_hours.get('acc_period', 0) + pc_dict[
                                'norm_hours_acc_period']
                            norm_hours['prev_months'] = norm_hours.get('prev_months', 0) + pc_dict[
                                'norm_hours_prev_months']
                            norm_hours['curr_month'] = norm_hours.get('curr_month', 0) + pc_dict[
                                'norm_hours_curr_month']
                            norm_hours['curr_month_end'] = norm_hours.get('curr_month_end', 0) + pc_dict[
                                'norm_hours_prev_months'] + pc_dict['norm_hours_curr_month']

                        empl_dict.setdefault('vacation_or_sick_plan_approved_count', {})[pc_dict['dt__month']] = \
                            norm_hours.get('vacation_or_sick_plan_approved_count', 0) + \
                            pc_dict['vacation_or_sick_plan_approved_count']
                        empl_dict.setdefault('vacation_or_sick_plan_approved_count_selected_period', {})[pc_dict['dt__month']] = \
                            norm_hours.get('vacation_or_sick_plan_approved_count_selected_period', 0) + \
                            pc_dict['vacation_or_sick_plan_approved_count_selected_period']

                    if is_fact_key == 'plan' and is_approved_key == 'approved':  # считаем только 1 раз
                        norm_hours_by_months = empl_dict.setdefault('norm_hours_by_months', {})
                        empl_days_count = empl_dict.setdefault('empl_days_count', {})
                        empl_days_count_selected_period = empl_dict.setdefault('empl_days_count_selected_period', {})
                        norm_hours_by_months[pc_dict['dt__month']] = norm_hours_by_months.get(
                            pc_dict['dt__month'], 0) + pc_dict['norm_hours_acc_period']
                        empl_dict['norm_hours_total'] = empl_dict.get(
                            'norm_hours_total', 0) + pc_dict['norm_hours_acc_period']
                        empl_days_count[pc_dict['dt__month']] = empl_days_count.get(
                            pc_dict['dt__month'], 0) + pc_dict['empl_days_count']
                        empl_days_count_selected_period[pc_dict['dt__month']] = empl_days_count_selected_period.get(
                            pc_dict['dt__month'], 0) + pc_dict['empl_days_count_selected_period']
                        empl_dict['period_start'] = pc_dict['period_start']
                        empl_dict['period_end'] = pc_dict['period_end']

        for worker_id, worker_dict in res.items():
            acc_period_months = list(range(self.acc_period_start.month, self.acc_period_end.month + 1))
            for empl in self.workers_dict.get(worker_id):
                empl_dict = res.setdefault(
                    worker_id, {}).setdefault('employments', {}).setdefault(empl.id, {})
                norm_hours_by_months = empl_dict.get('norm_hours_by_months', {})
                if empl.sawh_hours_by_months:
                    sawh_hours_sum = sum(
                        v for k, v in empl.sawh_hours_by_months.items() if int(k[1:]) in acc_period_months)
                    sawh_settings_base = {
                        int(k[1:]): v / sawh_hours_sum
                        for k, v in empl.sawh_hours_by_months.items() if int(k[1:]) in acc_period_months}
                    empl_dict['sawh_settings_base'] = sawh_settings_base

                    for month_num, empl_norm_hours in norm_hours_by_months.items():
                        _month_start, _month_end, days_in_month = get_month_range(
                            self.year, month_num, return_days_in_month=True)
                        empl_days_count = empl_dict.get('empl_days_count').get(month_num)
                        empl_dict.setdefault('sawh_settings_empl', {})[month_num] = \
                            empl_days_count / days_in_month * empl_dict['sawh_settings_base'][month_num] / sum(empl_dict['sawh_settings_base'].values())

                    for month_num, empl_norm_hours in norm_hours_by_months.items():
                        sawh_settings_empl_sum = sum(empl_dict['sawh_settings_empl'].values())
                        empl_dict.setdefault('sawh_settings_empl_normalized', {})[month_num] = empl_dict['sawh_settings_empl'][month_num] / sawh_settings_empl_sum
                        empl_dict.setdefault('sawh_hours_by_months', {})[month_num] = \
                            empl_dict['sawh_settings_empl_normalized'][month_num] * empl_dict['norm_hours_total']
                else:
                    empl_dict['sawh_hours_by_months'] = norm_hours_by_months

                for month_num, _norm_hours in norm_hours_by_months.items():
                    sawh_hours_by_months = empl_dict['sawh_hours_by_months'][month_num]
                    empl_dict.setdefault('one_day_value', {})[month_num] = \
                        sawh_hours_by_months / empl_dict.get('empl_days_count').get(month_num)
                    empl_dict.setdefault('sawh_hours_by_months_plan_approved', {})[month_num] = empl_dict['sawh_hours_by_months'][month_num] - (
                            empl_dict['one_day_value'][month_num] *
                            empl_dict.get('vacation_or_sick_plan_approved_count', {}).get(month_num, 0))
                    empl_dict.setdefault('sawh_hours_by_months_plan_not_approved', {})[month_num] = empl_dict['sawh_hours_by_months'][
                        month_num] - (empl_dict['one_day_value'][month_num] * empl_dict.get(
                        'vacation_or_sick_plan_not_approved_count', {}).get(month_num, 0))

                    if month_num in selected_period_months:
                        selected_period_hours = \
                            empl_dict['one_day_value'][month_num] * empl_dict['empl_days_count_selected_period'][month_num]
                        empl_dict.setdefault('sawh_hours_by_months_plan_approved_selected_period', {})[month_num] = \
                         selected_period_hours - (
                                empl_dict['one_day_value'][month_num] *
                                empl_dict.get('vacation_or_sick_plan_approved_count_selected_period', {}).get(month_num, 0))
                        empl_dict.setdefault('sawh_hours_by_months_plan_not_approved_selected_period', {})[month_num] = \
                        selected_period_hours - (
                                empl_dict['one_day_value'][month_num] *
                                empl_dict.get('vacation_or_sick_plan_not_approved_count_selected_period', {}).get(month_num, 0))

                empl_dict['sawh_hours_plan_approved_selected_period'] = sum(
                    empl_dict.setdefault('sawh_hours_by_months_plan_approved_selected_period', {}).values())
                empl_dict['sawh_hours_plan_not_approved_selected_period'] = sum(
                    empl_dict.setdefault('sawh_hours_by_months_plan_not_approved_selected_period', {}).values())

            work_hours_prev_months = worker_dict.get(
                'fact', {}).get('approved', {}).get('work_hours', {}).get('prev_months', 0)

            for is_fact_key in ['plan', 'fact']:
                for is_approved_key in ['approved', 'not_approved']:
                    overtime = worker_dict.setdefault(
                        is_fact_key, {}
                    ).setdefault(
                        is_approved_key, {}
                    ).setdefault(
                        'overtime', {}
                    )

                    sawh_hours = worker_dict.setdefault(
                        is_fact_key, {}
                    ).setdefault(
                        is_approved_key, {}
                    ).setdefault(
                        'sawh_hours', {}
                    )
                    if is_fact_key == 'plan' and is_approved_key == 'not_approved':
                        for empl_id, empl_dict in worker_dict.get('employments', {}).items():
                            for month_num in acc_period_months:
                                sawh_hours.setdefault('by_months', {})[month_num] = \
                                    sawh_hours.get('by_months', {}).get(month_num, 0) + \
                                    empl_dict.get('sawh_hours_by_months_plan_not_approved', {}).get(month_num, 0)

                    else:
                        for empl_id, empl_dict in worker_dict.get('employments', {}).items():
                            for month_num in acc_period_months:
                                sawh_hours.setdefault('by_months', {})[month_num] = \
                                    sawh_hours.get('by_months', {}).get(month_num, 0) + \
                                    empl_dict.get('sawh_hours_by_months_plan_approved', {}).get(month_num, 0)

                    sawh_hours['curr_month'] = sawh_hours['by_months'].get(curr_month)
                    work_hours_curr_month = worker_dict.get(
                        is_fact_key).get(is_approved_key).get('work_hours', {}).get('total', 0)
                    work_hours_until_acc_period_end = worker_dict.get(
                        is_fact_key).get(is_approved_key).get('work_hours', {}).get('until_acc_period_end', 0)
                    norm_hours_acc_period = worker_dict.get(
                        is_fact_key).get(is_approved_key).get('norm_hours', {}).get('acc_period', 0)
                    norm_hours_curr_month = worker_dict.get(
                        is_fact_key).get(is_approved_key).get('norm_hours', {}).get('curr_month', 0)
                    norm_hours_prev_months = worker_dict.get(
                        is_fact_key).get(is_approved_key).get('norm_hours', {}).get('prev_months', 0)
                    norm_hours_curr_month_end = worker_dict.get(
                        is_fact_key).get(is_approved_key).get('norm_hours', {}).get('curr_month_end', 0)

                    overtime['acc_period'] = (
                        work_hours_prev_months + work_hours_until_acc_period_end) - norm_hours_acc_period
                    overtime['prev_months'] = work_hours_prev_months - norm_hours_prev_months
                    overtime['curr_month'] = work_hours_curr_month - norm_hours_curr_month
                    overtime['curr_month_end'] = (
                        work_hours_prev_months + work_hours_curr_month) - norm_hours_curr_month_end

        return res
