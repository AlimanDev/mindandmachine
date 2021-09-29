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
    FloatField,
)
from django.db.models.expressions import RawSQL
from django.db.models.functions import Cast, TruncDate
from django.db.models.functions import Extract, Coalesce, Greatest, Least
from django.utils.functional import cached_property

from src.base.models import Employment, Shop, ProductionDay, SAWHSettings, Network
from src.forecast.models import PeriodClients
from src.timetable.models import WorkerDay, ProdCal, Timesheet, WorkerDayType


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
        employee_id=OuterRef('employee_id'),
        shop_id=shop_id,
        dt_hired__lte=OuterRef('dt'))

    emp_subq = Employment.objects.filter(
        Q(dt_fired__gte=OuterRef('dt')) | Q(dt_fired__isnull=True),
        employee_id=OuterRef('employee_id'),
        dt_hired__lte=OuterRef('dt')
    ).exclude(
        shop_id=shop_id
    )

    plan_approved_subq = WorkerDay.objects.filter(
        dt=OuterRef('dt'),
        is_fact=False,
        is_approved=True,
        employee_id=OuterRef('employee_id'),
        type_id=WorkerDay.TYPE_WORKDAY,
    )

    not_approved_subq = WorkerDay.objects.filter(
        dt=OuterRef('dt'),
        is_fact=OuterRef('is_fact'),
        is_approved=False,
        parent_worker_day_id=OuterRef('id'),
    )
    cond = Q()
    if 'employee_id__in' in data and data['employee_id__in'] is not None:
        cond = Q(employee_id__in=data['employee_id__in'])

    worker_days = WorkerDay.objects.filter(
        cond,
        dt__gte=dt_start,
        dt__lte=dt_end,
        shop_id=shop_id,
        type_id=WorkerDay.TYPE_WORKDAY,
        # employee_id__isnull=False,
    ).annotate(
        has_employee=Case(When(employee_id__isnull=True, then=Value(False)), default=Value(True),
                        output_field=BooleanField()),

        salary=Coalesce(Subquery(emp_subq_shop.values('salary')[:1]), Subquery(emp_subq.values('salary')[:1]), 0),
        is_shop=Exists(emp_subq_shop),
        has_plan=Exists(plan_approved_subq),
    ).filter(
        Q(is_fact=False) | Q(has_plan=True)
    )

    worker_days_stat = worker_days.values(
        'dt', 'is_fact', 'is_approved', 'is_shop', 'has_employee'
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
        has_employee = day.pop('has_employee')
        shop = 'shop' if is_shop else \
            'outsource' if has_employee else \
                'vacancies'

        stat[dt][plan_or_fact][approved][shop] = day

    worker_days_combined = worker_days.annotate(
        has_na_child=Exists(not_approved_subq)).filter(
        Q(is_approved=False) | Q(has_na_child=False)
    ).values(
        'dt', 'is_fact', 'is_shop', 'has_employee'
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
        has_employee = day.pop('has_employee')
        is_shop = day.pop('is_shop')
        shop = 'shop' if is_shop else \
            'outsource' if has_employee else \
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
    def __init__(self, dt_from, dt_to, employee_id=None, employee_id__in=None, network=None, shop_id=None,
                 hours_by_types: list = None):
        """
        :param dt_from:
        :param dt_to:
        :param employee_id:
        :param employee_id__in:
        :param network:
        :param shop_id: для какого магазина статистика + для определения сотрудников
            (если явно не переданы в employee_id или в employee_id__in)
        """
        assert shop_id or network
        self.shop_id = shop_id
        self.dt_from = dt_from
        self.dt_to = dt_to
        self.employee_id = employee_id
        self.employee_id__in = employee_id__in.split(',') if isinstance(employee_id__in, str) else employee_id__in
        self.year = dt_from.year
        self.month = dt_from.month
        self.hours_by_types = hours_by_types or list(WorkerDayType.objects.filter(
            is_active=True,
            show_stat_in_hours=True,
        ).values_list('code', flat=True))
        self._network = network

    @cached_property
    def shop(self):
        return Shop.objects.filter(id=self.shop_id).first()

    @cached_property
    def network(self):
        return self._network or self.shop.network

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
        ).select_related(
            'position'
        ).order_by(
            'dt_hired'
        ).annotate(
            sawh_hours_by_months=RawSQL("""SELECT V5."work_hours_by_months"
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
                 LIMIT 1""", (self.year,)),
            sawh_settings_type=RawSQL("""SELECT V5."type"
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
                 LIMIT 1""", (self.year,))
        ).distinct()
        # в django 2 есть баг, при переходе на django 3 можно будет использовать следующий annotate
        # ).annotate(
        #     sawh_hours_by_months=Subquery(SAWHSettingsMapping.objects.filter(
        #         Q(positions__id=OuterRef('position_id')) | Q(shops__id=OuterRef('shop_id')),
        #         ~Q(exclude_positions__id=OuterRef('position_id')),
        #         year=self.year,
        #     ).order_by('-priority').values('sawh_settings__work_hours_by_months')[:1])
        # ).distinct()
        if self.employee_id:
            employments = employments.filter(employee_id=self.employee_id)
        elif self.employee_id__in:
            employments = employments.filter(employee_id__in=self.employee_id__in)
        elif self.shop_id:
            employments = employments.filter(employee__employments__shop_id=self.shop_id)

        return list(employments)

    @cached_property
    def employees_dict(self):
        employees_dict = {}
        for e in self.employments_list:
            employees_dict.setdefault(e.employee_id, []).append(e)
        return employees_dict

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
        outside_of_selected_period_q = Q(Q(dt__lt=self.dt_from) | Q(dt__gt=self.dt_to))

        selected_period_months = self._get_selected_period_months()
        prev_months = list(range(prev_months_dt_from.month, prev_months_dt_to.month + 1))
        curr_month = self.dt_from.month
        months_until_acc_period_end = list(range(until_acc_period_end_dt_from.month, until_acc_period_end_dt_to.month + 1))

        work_days = WorkerDay.objects.filter(
            dt__gte=acc_period_dt_from,
            dt__lte=acc_period_dt_to,
            employee_id__in=self.employees_dict.keys(),
        ).values(
            'employee_id',
            'employment_id',
            'is_fact',
            'is_approved',
            'dt__month',
        ).annotate(
            work_days_selected_shop=Coalesce(Count('id', filter=Q(selected_period_q, shop_id=self.shop_id,
                                                                  work_hours__gte=timedelta(0),
                                                                  type__is_dayoff=False, type__is_work_hours=True)), 0),
            work_days_other_shops=Coalesce(Count('id', filter=Q(selected_period_q, ~Q(shop_id=self.shop_id),
                                                                work_hours__gte=timedelta(0),
                                                                type__is_dayoff=False, type__is_work_hours=True)), 0),
            work_days_selected_period=Coalesce(Count('id', filter=Q(selected_period_q, work_hours__gte=timedelta(0),
                                                          type__is_dayoff=False, type__is_work_hours=True)), 0),
            work_hours_selected_shop=Coalesce(Sum(Extract(F('work_hours'), 'epoch') / 3600,
                                                  filter=Q(selected_period_q, shop_id=self.shop_id,
                                                           work_hours__gte=timedelta(0),
                                                           type__is_dayoff=False, type__is_work_hours=True),
                                                  output_field=FloatField()), 0),
            work_hours_other_shops=Coalesce(Sum(Extract(F('work_hours'), 'epoch') / 3600,
                                                filter=Q(selected_period_q, ~Q(shop_id=self.shop_id),
                                                         work_hours__gte=timedelta(0),
                                                         type__is_dayoff=False, type__is_work_hours=True),
                                                output_field=FloatField()), 0),
            work_hours_selected_period=Coalesce(Sum(Extract(F('work_hours'), 'epoch') / 3600,
                                          filter=Q(selected_period_q, work_hours__gte=timedelta(0),
                                                   type__is_dayoff=False, type__is_work_hours=True),
                                          output_field=FloatField()), 0),
            work_hours_total=Coalesce(Sum(Extract(F('work_hours'), 'epoch') / 3600,
                                                filter=Q(work_hours__gte=timedelta(0),
                                                         type__is_dayoff=False, type__is_work_hours=True),
                                                output_field=FloatField()), 0),
            work_hours_until_acc_period_end=Coalesce(Sum(Extract(F('work_hours'), 'epoch') / 3600,
                                                         filter=Q(until_acc_period_end_q, work_hours__gte=timedelta(0),
                                                                  type__is_dayoff=False, type__is_work_hours=True),
                                                         output_field=FloatField()), 0),
            work_hours_outside_of_selected_period=Coalesce(Sum(Extract(F('work_hours'), 'epoch') / 3600,
                                                         filter=Q(outside_of_selected_period_q, work_hours__gte=timedelta(0),
                                                                  type__is_dayoff=False, type__is_work_hours=True),
                                                         output_field=FloatField()), 0)
        ).order_by('employee_id', '-is_fact', '-is_approved')  # такая сортировка нужна для work_hours_prev_months
        if self.hours_by_types:
            work_days = work_days.annotate(**{
                'hours_by_type_{}'.format(type_id): Coalesce(Sum(Extract(F('work_hours'), 'epoch') / 3600,
                                          filter=Q(selected_period_q, work_hours__gte=timedelta(0), type_id=type_id),
                                          output_field=FloatField()), 0) for type_id in self.hours_by_types
            })
        for wd_dict in work_days:
            empl_dict = res.setdefault(
                wd_dict['employee_id'], {}).setdefault('employments', {}).setdefault(wd_dict['employment_id'], {})
            data = res.setdefault(
                wd_dict['employee_id'], {}
            ).setdefault(
                self._get_is_fact_key(wd_dict['is_fact']), {}
            ).setdefault(
                self._get_is_approved_key(wd_dict['is_approved']), {}
            )
            work_days_dict = data.setdefault('work_days', {})
            work_days_dicts = [work_days_dict]
            for work_days in work_days_dicts:
                work_days['selected_shop'] = work_days.get('selected_shop', 0) + wd_dict['work_days_selected_shop']
                work_days['other_shops'] = work_days.get('other_shops', 0) + wd_dict['work_days_other_shops']
                work_days['total'] = work_days.get('total', 0) + wd_dict['work_days_selected_period']

            work_hours_dict = data.setdefault('work_hours', {})
            work_hours_dicts = [work_hours_dict]
            for work_hours in work_hours_dicts:
                work_hours['selected_shop'] = work_hours.get('selected_shop', 0) + wd_dict['work_hours_selected_shop']
                work_hours['other_shops'] = work_hours.get('other_shops', 0) + wd_dict['work_hours_other_shops']
                work_hours['total'] = work_hours.get('total', 0) + wd_dict['work_hours_selected_period']
                work_hours['until_acc_period_end'] = work_hours.get(
                    'until_acc_period_end', 0) + wd_dict['work_hours_until_acc_period_end']

            if self.hours_by_types:
                hours_by_type_dict = data.setdefault('hours_by_type', {})
                for type_id in self.hours_by_types:
                    hours_by_type_dict[type_id] = hours_by_type_dict.get(type_id, 0) + wd_dict[f'hours_by_type_{type_id}']

            # за прошлые месяцы отработанные часы берем из факта подтвержденного
            if self.network.prev_months_work_hours_source == Network.WD_FACT_APPROVED \
                    and wd_dict['is_fact'] and wd_dict['is_approved'] and wd_dict['dt__month'] in prev_months:
                for work_hours in work_hours_dicts:
                    work_hours['prev_months'] = work_hours.get('prev_months', 0) + wd_dict['work_hours_total']
                empl_dict['work_hours_prev_months'] = empl_dict.get('work_hours_prev_months', 0) + wd_dict[
                    'work_hours_total']

            if not wd_dict['is_fact'] and wd_dict['is_approved']:
                empl_dict.setdefault('work_hours_outside_of_selected_period_plan_approved', {})[wd_dict['dt__month']] = empl_dict.get(
                    'work_hours_outside_of_selected_period_plan_approved', {}).get(wd_dict['dt__month'], 0) + wd_dict['work_hours_outside_of_selected_period']

            if not wd_dict['is_fact'] and not wd_dict['is_approved']:
                empl_dict.setdefault('work_hours_outside_of_selected_period_plan_not_approved', {})[wd_dict['dt__month']] = empl_dict.get(
                    'work_hours_outside_of_selected_period_plan_not_approved', {}).get(wd_dict['dt__month'], 0) + wd_dict['work_hours_outside_of_selected_period']

        if self.network.prev_months_work_hours_source in [Network.FACT_TIMESHEET, Network.MAIN_TIMESHEET]:
            hours_field_name_mapping = {
                Network.FACT_TIMESHEET: ('fact_timesheet_total_hours', 'fact_timesheet_type'),
                Network.MAIN_TIMESHEET: ('main_timesheet_total_hours', 'main_timesheet_type'),
            }
            hours_field, type_field = hours_field_name_mapping.get(self.network.prev_months_work_hours_source)

            timesheet_prev_months_work_hours = list(Timesheet.objects.filter(
                prev_months_q,
                employee_id__in=self.employees_dict.keys(),
                **{f'{type_field}__is_work_hours': True},
            ).values(
                'employee_id',
            ).annotate(
                prev_months_work_hours=Sum(hours_field),
            ).values_list('employee_id', 'prev_months_work_hours'))

            for is_fact_key in ['plan', 'fact']:
                for is_approved_key in ['approved', 'not_approved']:
                    for employee_id, prev_months_work_hours in timesheet_prev_months_work_hours:
                        res.setdefault(
                            employee_id, {}
                        ).setdefault(
                            is_fact_key, {}
                        ).setdefault(
                            is_approved_key, {}
                        ).setdefault(
                            'work_hours', {}
                        )['prev_months'] = float(prev_months_work_hours or 0)

        for employee_id in self.employees_dict.keys():
            employee_dict = res.setdefault(
                employee_id, {}
            )
            worker_work_hours_prev_months = employee_dict.get(
                'fact', {}).get('approved', {}).get('work_hours', {}).get('prev_months', 0)

            for is_fact_key in ['plan', 'fact']:
                for is_approved_key in ['approved', 'not_approved']:
                    worker_data = employee_dict.setdefault(
                        is_fact_key, {}
                    ).setdefault(
                        is_approved_key, {}
                    )

                    data_list = [(worker_data, worker_work_hours_prev_months)]

                    employees = employee_dict.get('employees', {})
                    for empl_key, empl_dict in employees.items():
                        empl_work_hours_prev_months = empl_dict.get(
                            'fact', {}).get('approved', {}).get('work_hours', {}).get('prev_months', 0)

                        empl_data = empl_dict.get(
                            is_fact_key, {}
                        ).get(
                            is_approved_key, {}
                        )
                        if empl_data:
                            data_list.append((empl_data, empl_work_hours_prev_months))

                    for data, work_hours_prev_months in data_list:
                        work_hours = data.setdefault('work_hours', {})
                        if is_fact_key == 'fact' and is_approved_key == 'approved':
                            pass
                        else:
                            work_hours['prev_months'] = work_hours_prev_months
                        work_hours['acc_period'] = work_hours_prev_months + work_hours.get('until_acc_period_end', 0)

        work_days = WorkerDay.objects.filter(
            dt__gte=acc_period_dt_from,
            dt__lte=acc_period_dt_to,
            employee_id__in=self.employees_dict.keys(),
        ).values(
            'employee_id',
            'employment_id',
            'is_fact',
            'is_approved',
            'type_id',
            'dt__month',
        ).annotate(
            day_type_count=Count('type_id', filter=selected_period_q),
            any_day_count_outside_of_selected_period=Count(
                'type_id', filter=outside_of_selected_period_q),
            workdays_count_outside_of_selected_period=Count(
                'type_id', filter=Q(outside_of_selected_period_q, Q(
                    Q(type__is_dayoff=False, type__is_work_hours=True) | Q(type_id=WorkerDay.TYPE_HOLIDAY)))),
        )
        for wd_dict in work_days:
            data = res.setdefault(
                wd_dict['employee_id'], {}
            ).setdefault(
                self._get_is_fact_key(wd_dict['is_fact']), {}
            ).setdefault(
                self._get_is_approved_key(wd_dict['is_approved']), {}
            )

            if wd_dict['dt__month'] == curr_month:
                day_type = data.setdefault('day_type', {})
                day_type[wd_dict['type_id']] = wd_dict['day_type_count']

            if not wd_dict['is_fact']:
                days_count_outside_of_selected_period = data.setdefault('workdays_count_outside_of_selected_period', {})
                days_count_outside_of_selected_period[wd_dict['dt__month']] = days_count_outside_of_selected_period.get(
                    wd_dict['dt__month'], 0) + wd_dict['workdays_count_outside_of_selected_period']
                any_day_count_outside_of_selected_period = data.setdefault('any_day_count_outside_of_selected_period', {})
                any_day_count_outside_of_selected_period[wd_dict['dt__month']] = any_day_count_outside_of_selected_period.get(
                    wd_dict['dt__month'], 0) + wd_dict['any_day_count_outside_of_selected_period']

        prod_cal_qs = ProdCal.objects.filter(
            dt__gte=acc_period_dt_from,
            dt__lte=acc_period_dt_to,
            employee_id__in=self.employees_dict.keys(),
        ).values(
            'employee_id',
            'employment_id',
            'dt__month',
        ).annotate(
            period_start=Greatest('employment__dt_hired', Value(acc_period_dt_from)),
            period_end=Least('employment__dt_fired', Value(acc_period_dt_to)),
            has_vacation_or_sick_plan_approved=Exists(WorkerDay.objects.filter(
                employee_id=OuterRef('employee_id'),
                employment_id=OuterRef('employment_id'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=True,
                type__is_reduce_norm=True,
            )),
            vacation_or_sick_plan_approved_count=Count(Subquery(WorkerDay.objects.filter(
                employee_id=OuterRef('employee_id'),
                employment_id=OuterRef('employment_id'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=True,
                type__is_reduce_norm=True,
            ).values('id'))),
            vacation_or_sick_plan_approved_count_selected_period=Count(Subquery(WorkerDay.objects.filter(
                selected_period_q,
                employee_id=OuterRef('employee_id'),
                employment_id=OuterRef('employment_id'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=True,
                type__is_reduce_norm=True,
            ).values('id'))),
            has_vacation_or_sick_plan_not_approved=Exists(WorkerDay.objects.filter(
                employee_id=OuterRef('employee_id'),
                employment_id=OuterRef('employment_id'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=False,
                type__is_reduce_norm=True,
            )),
            vacation_or_sick_plan_not_approved_count=Count(Subquery(WorkerDay.objects.filter(
                employee_id=OuterRef('employee_id'),
                employment_id=OuterRef('employment_id'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=False,
                type__is_reduce_norm=True,
            ).values('id'))),
            vacation_or_sick_plan_not_approved_count_selected_period=Count(Subquery(WorkerDay.objects.filter(
                selected_period_q,
                employee_id=OuterRef('employee_id'),
                employment_id=OuterRef('employment_id'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=False,
                type__is_reduce_norm=True,
            ).values('id'))),
            norm_hours_acc_period=Coalesce(
                Sum('norm_hours'), 0),
            norm_hours_prev_months=Coalesce(
                Sum('norm_hours', filter=prev_months_q), 0),
            norm_hours_curr_month=Coalesce(
                Sum('norm_hours', filter=curr_month_q), 0),
            norm_hours_curr_month_end=Coalesce(
                Sum('norm_hours', filter=curr_month_end_q), 0),
            norm_hours_selected_period=Coalesce(
                Sum('norm_hours', filter=selected_period_q), 0),
            empl_days_count=Count('dt'),
            empl_days_count_selected_period=Count('dt', filter=selected_period_q),
            empl_days_count_outside_of_selected_period=Count('dt', filter=outside_of_selected_period_q),
        )

        for pc_dict in prod_cal_qs:
            for is_fact_key in ['plan', 'fact']:
                for is_approved_key in ['approved', 'not_approved']:
                    data = res.setdefault(
                        pc_dict['employee_id'], {}
                    ).setdefault(
                        is_fact_key, {}
                    ).setdefault(
                        is_approved_key, {}
                    )

                    worker_norm_hours = data.setdefault('norm_hours', {})
                    empl_dict = res.setdefault(
                        pc_dict['employee_id'], {}).setdefault('employments', {}).setdefault(pc_dict['employment_id'], {})

                    if is_fact_key == 'plan' and is_approved_key == 'not_approved':
                        if pc_dict['has_vacation_or_sick_plan_not_approved'] is False:
                            for norm_hours in [worker_norm_hours]:
                                norm_hours['acc_period'] = norm_hours.get('acc_period', 0) + pc_dict[
                                    'norm_hours_acc_period']
                                norm_hours['selected_period'] = norm_hours.get('selected_period', 0) + pc_dict[
                                    'norm_hours_selected_period']
                                norm_hours['prev_months'] = norm_hours.get('prev_months', 0) + pc_dict[
                                    'norm_hours_prev_months']
                                norm_hours['curr_month'] = norm_hours.get('curr_month', 0) + pc_dict[
                                    'norm_hours_curr_month']
                                norm_hours['curr_month_end'] = norm_hours.get('curr_month_end', 0) + pc_dict[
                                    'norm_hours_prev_months'] + pc_dict['norm_hours_curr_month']

                        empl_dict.setdefault('vacation_or_sick_plan_not_approved_count', {})[pc_dict['dt__month']] = \
                            worker_norm_hours.get('vacation_or_sick_plan_not_approved_count', 0) + \
                            pc_dict['vacation_or_sick_plan_not_approved_count']
                        empl_dict.setdefault('vacation_or_sick_plan_not_approved_count_selected_period', {})[pc_dict['dt__month']] = \
                            worker_norm_hours.get('vacation_or_sick_plan_not_approved_count_selected_period', 0) + \
                            pc_dict['vacation_or_sick_plan_not_approved_count_selected_period']
                        empl_dict.setdefault('vacation_or_sick_plan_not_approved_count_outside_of_selected_period', {})[
                            pc_dict['dt__month']] = empl_dict.setdefault('vacation_or_sick_plan_not_approved_count', {})[
                                                        pc_dict['dt__month']] - empl_dict.setdefault(
                            'vacation_or_sick_plan_not_approved_count_selected_period', {})[pc_dict['dt__month']]
                    else:
                        if pc_dict['has_vacation_or_sick_plan_approved'] is False:
                            for norm_hours in [worker_norm_hours]:
                                norm_hours['acc_period'] = norm_hours.get('acc_period', 0) + pc_dict[
                                    'norm_hours_acc_period']
                                norm_hours['selected_period'] = norm_hours.get('selected_period', 0) + pc_dict[
                                    'norm_hours_selected_period']
                                norm_hours['prev_months'] = norm_hours.get('prev_months', 0) + pc_dict[
                                    'norm_hours_prev_months']
                                norm_hours['curr_month'] = norm_hours.get('curr_month', 0) + pc_dict[
                                    'norm_hours_curr_month']
                                norm_hours['curr_month_end'] = norm_hours.get('curr_month_end', 0) + pc_dict[
                                    'norm_hours_prev_months'] + pc_dict['norm_hours_curr_month']

                        empl_dict.setdefault('vacation_or_sick_plan_approved_count', {})[pc_dict['dt__month']] = \
                            worker_norm_hours.get('vacation_or_sick_plan_approved_count', 0) + \
                            pc_dict['vacation_or_sick_plan_approved_count']
                        empl_dict.setdefault('vacation_or_sick_plan_approved_count_selected_period', {})[pc_dict['dt__month']] = \
                            worker_norm_hours.get('vacation_or_sick_plan_approved_count_selected_period', 0) + \
                            pc_dict['vacation_or_sick_plan_approved_count_selected_period']
                        empl_dict.setdefault('vacation_or_sick_plan_approved_count_outside_of_selected_period', {})[
                            pc_dict['dt__month']] = empl_dict.setdefault('vacation_or_sick_plan_approved_count', {})[
                                                        pc_dict['dt__month']] - empl_dict.setdefault(
                            'vacation_or_sick_plan_approved_count_selected_period', {})[pc_dict['dt__month']]

                    if is_fact_key == 'plan' and is_approved_key == 'approved':  # считаем только 1 раз
                        norm_hours_by_months = empl_dict.setdefault('norm_hours_by_months', {})
                        empl_days_count = empl_dict.setdefault('empl_days_count', {})
                        empl_days_count_selected_period = empl_dict.setdefault('empl_days_count_selected_period', {})
                        empl_days_count_outside_of_selected_period = empl_dict.setdefault('empl_days_count_outside_of_selected_period', {})
                        norm_hours_by_months[pc_dict['dt__month']] = norm_hours_by_months.get(
                            pc_dict['dt__month'], 0) + pc_dict['norm_hours_acc_period']
                        empl_dict['norm_hours_total'] = empl_dict.get(
                            'norm_hours_total', 0) + pc_dict['norm_hours_acc_period']
                        empl_days_count[pc_dict['dt__month']] = empl_days_count.get(
                            pc_dict['dt__month'], 0) + pc_dict['empl_days_count']
                        empl_days_count_selected_period[
                            pc_dict['dt__month']] = empl_days_count_selected_period.get(
                            pc_dict['dt__month'], 0) + pc_dict['empl_days_count_selected_period']
                        empl_days_count_outside_of_selected_period[pc_dict['dt__month']] = empl_days_count_outside_of_selected_period.get(
                            pc_dict['dt__month'], 0) + pc_dict['empl_days_count_outside_of_selected_period']
                        empl_dict['period_start'] = pc_dict['period_start']
                        empl_dict['period_end'] = pc_dict['period_end']
                        empl_dict['norm_hours_until_acc_period_end'] = empl_dict[
                           'norm_hours_total'] - empl_dict.get('work_hours_prev_months', 0)

        for employee_id, employee_dict in res.items():
            acc_period_months = list(range(self.acc_period_start.month, self.acc_period_end.month + 1))
            for empl in self.employees_dict.get(employee_id, []):
                empl_dict = res.setdefault(
                    employee_id, {}).setdefault('employments', {}).setdefault(empl.id, {})
                norm_hours_by_months = empl_dict.get('norm_hours_by_months', {})
                if empl.sawh_hours_by_months and empl.sawh_settings_type == SAWHSettings.PART_OF_PROD_CAL_SUMM:
                    sawh_hours_sum = sum(
                        v for k, v in empl.sawh_hours_by_months.items() if int(k[1:]) in acc_period_months)
                    sawh_settings_base = {
                        int(k[1:]): v / sawh_hours_sum
                        for k, v in empl.sawh_hours_by_months.items() if int(k[1:]) in acc_period_months}
                    empl_dict['sawh_settings_base'] = sawh_settings_base

                    for month_num in norm_hours_by_months.keys():
                        _month_start, _month_end, days_in_month = get_month_range(
                            self.year, month_num, return_days_in_month=True)
                        empl_days_count = empl_dict.get('empl_days_count').get(month_num)
                        empl_dict.setdefault('sawh_settings_empl', {})[month_num] = \
                            empl_days_count / days_in_month * empl_dict['sawh_settings_base'][month_num] / sum(empl_dict['sawh_settings_base'].values())

                    for month_num in norm_hours_by_months.keys():
                        sawh_settings_empl_sum = sum(empl_dict['sawh_settings_empl'].values())
                        empl_dict.setdefault('sawh_settings_empl_normalized', {})[month_num] = empl_dict['sawh_settings_empl'][month_num] / sawh_settings_empl_sum
                        empl_dict.setdefault('sawh_hours_by_months', {})[month_num] = \
                            empl_dict['sawh_settings_empl_normalized'][month_num] * empl_dict['norm_hours_total']
                elif empl.sawh_hours_by_months and empl.sawh_settings_type == SAWHSettings.FIXED_HOURS:
                    for month_num, prod_cal_norm_hours in norm_hours_by_months.items():
                        _month_start, _month_end, days_in_month = get_month_range(
                            self.year, month_num, return_days_in_month=True)
                        empl_days_count = empl_dict.get('empl_days_count').get(month_num, 0)
                        empl_dict.setdefault('sawh_hours_by_months', {})[
                            month_num] = (empl_days_count / days_in_month) * (empl.norm_work_hours / 100) * empl.sawh_hours_by_months.get(
                            f'm{month_num}', prod_cal_norm_hours)
                else:
                    empl_dict['sawh_hours_by_months'] = norm_hours_by_months

                for month_num in [m for m in months_until_acc_period_end if m in empl_dict['sawh_hours_by_months']]:
                    if self.network.consider_remaining_hours_in_prev_months_when_calc_norm_hours:
                        sawh_settings_empl_sum = sum(
                            v for k, v in empl_dict['sawh_hours_by_months'].items() if k in months_until_acc_period_end)
                        empl_dict.setdefault('sawh_settings_empl_normalized', {})[month_num] = \
                            (empl_dict['sawh_hours_by_months'][month_num] / sawh_settings_empl_sum) if sawh_settings_empl_sum else 0
                        empl_dict.setdefault('sawh_hours_by_months', {})[month_num] = \
                            empl_dict['sawh_settings_empl_normalized'][month_num] * empl_dict[
                                'norm_hours_until_acc_period_end']
                        empl_dict.setdefault('one_day_value', {})[month_num] = empl_dict['sawh_hours_by_months'][month_num] / empl_dict['empl_days_count'][month_num]
                        empl_dict.setdefault('sawh_hours_by_months_plan_approved', {})[month_num] = \
                        empl_dict['sawh_hours_by_months'][month_num] - (
                                empl_dict['one_day_value'][month_num] *
                                empl_dict.get('vacation_or_sick_plan_approved_count', {}).get(month_num, 0))
                        empl_dict.setdefault('sawh_hours_by_months_plan_not_approved', {})[month_num] = \
                        empl_dict['sawh_hours_by_months'][
                            month_num] - (empl_dict['one_day_value'][month_num] * empl_dict.get(
                            'vacation_or_sick_plan_not_approved_count', {}).get(month_num, 0))
                    else:
                        sawh_hours_by_months = empl_dict['sawh_hours_by_months'][month_num]
                        empl_dict.setdefault('one_day_value', {})[month_num] = \
                            sawh_hours_by_months / empl_dict.get('empl_days_count').get(month_num)
                        empl_dict.setdefault('sawh_hours_by_months_plan_approved', {})[month_num] = \
                        empl_dict['sawh_hours_by_months'][month_num] - (
                                empl_dict['one_day_value'][month_num] *
                                empl_dict.get('vacation_or_sick_plan_approved_count', {}).get(month_num, 0))
                        empl_dict.setdefault('sawh_hours_by_months_plan_not_approved', {})[month_num] = \
                        empl_dict['sawh_hours_by_months'][
                            month_num] - (empl_dict['one_day_value'][month_num] * empl_dict.get(
                            'vacation_or_sick_plan_not_approved_count', {}).get(month_num, 0))

                    if month_num in selected_period_months:
                        days_count_in_month = empl_dict['empl_days_count'][month_num]
                        month_sawh_hours = empl_dict['sawh_hours_by_months'][month_num]
                        days_count_selected_period = empl_dict['empl_days_count_selected_period'][month_num]
                        days_count_outside_of_selected_period = empl_dict['empl_days_count_outside_of_selected_period'][month_num]

                        # approved
                        workdays_count_outside_of_selected_period_pa = res.get(employee_id, {}).get('plan', {}).get(
                            'approved', {}).get('workdays_count_outside_of_selected_period', {}).get(month_num, 0)
                        any_day_count_outside_of_selected_period_pa = res.get(employee_id, {}).get('plan', {}).get(
                            'approved', {}).get('any_day_count_outside_of_selected_period', {}).get(month_num, 0)
                        empty_days_pa = empl_dict['empl_days_count_outside_of_selected_period'][month_num] - any_day_count_outside_of_selected_period_pa
                        vacations_or_sick_count_selected_period_pa = empl_dict.get(
                            'vacation_or_sick_plan_approved_count_selected_period', {}).get(month_num, 0)
                        vacations_or_sick_count_outside_of_selected_period_pa = empl_dict.get(
                            'vacation_or_sick_plan_approved_count_outside_of_selected_period', {}).get(month_num, 0)
                        work_hours_outside_of_selected_period_pa = empl_dict.setdefault(
                            'work_hours_outside_of_selected_period_plan_approved', {}).get(month_num, 0)

                        fot1 = month_sawh_hours
                        fot2 = fot1 * ((days_count_selected_period - vacations_or_sick_count_selected_period_pa) / days_count_in_month)
                        fot3 = fot1 * (days_count_outside_of_selected_period - vacations_or_sick_count_outside_of_selected_period_pa) / days_count_in_month

                        # TODO: workdays_count_outside_of_selected_period_pa смотрится по сотруднику, а empty_days_pa по трудоустройству, некорректное сравнение
                        if workdays_count_outside_of_selected_period_pa == 0 or (workdays_count_outside_of_selected_period_pa + empty_days_pa) == 0 or (days_count_selected_period + empty_days_pa) == 0:
                            norm_work_amount = fot2
                        else:
                            had_to_work_outside_of_period = fot3 * (
                                workdays_count_outside_of_selected_period_pa / (workdays_count_outside_of_selected_period_pa + empty_days_pa))
                            remaining_work_outside_of_period = had_to_work_outside_of_period - work_hours_outside_of_selected_period_pa

                            norm_work_amount = fot2 + (remaining_work_outside_of_period * (
                                days_count_selected_period / (days_count_selected_period + empty_days_pa)))
                        empl_dict.setdefault('sawh_hours_by_months_plan_approved_selected_period', {})[month_num] = norm_work_amount

                        # not approved
                        workdays_count_outside_of_selected_period_npa = res.get(employee_id, {}).get('plan', {}).get(
                            'not_approved', {}).get('workdays_count_outside_of_selected_period', {}).get(month_num, 0)
                        any_day_count_outside_of_selected_period_npa = res.get(employee_id, {}).get('plan', {}).get(
                            'not_approved', {}).get('any_day_count_outside_of_selected_period', {}).get(month_num, 0)
                        empty_days_npa = empl_dict['empl_days_count_outside_of_selected_period'][
                                            month_num] - any_day_count_outside_of_selected_period_npa
                        vacations_or_sick_count_selected_period_npa = empl_dict.get(
                            'vacation_or_sick_plan_not_approved_count_selected_period', {}).get(month_num, 0)
                        vacations_or_sick_count_outside_of_selected_period_npa = empl_dict.get(
                            'vacation_or_sick_plan_not_approved_count_outside_of_selected_period', {}).get(month_num, 0)
                        work_hours_outside_of_selected_period_npa = empl_dict.setdefault(
                            'work_hours_outside_of_selected_period_plan_not_approved', {}).get(month_num, 0)

                        fot1 = month_sawh_hours
                        fot2 = fot1 * ((days_count_selected_period - vacations_or_sick_count_selected_period_npa) / days_count_in_month)
                        fot3 = fot1 * (
                                    days_count_outside_of_selected_period - vacations_or_sick_count_outside_of_selected_period_npa) / days_count_in_month

                        # TODO: workdays_count_outside_of_selected_period_npa смотрится по сотруднику, а empty_days_npa по трудоустройству, некорректное сравнение
                        if workdays_count_outside_of_selected_period_npa == 0 or (workdays_count_outside_of_selected_period_npa + empty_days_npa) == 0 or (days_count_selected_period + empty_days_npa) == 0:
                            norm_work_amount = fot2
                        else:
                            had_to_work_outside_of_period = fot3 * (
                                    workdays_count_outside_of_selected_period_npa / (workdays_count_outside_of_selected_period_npa + empty_days_npa))
                            remaining_work_outside_of_period = had_to_work_outside_of_period - work_hours_outside_of_selected_period_npa

                            norm_work_amount = fot2 + (remaining_work_outside_of_period * (
                                days_count_selected_period / (days_count_selected_period + empty_days_npa)))
                        empl_dict.setdefault('sawh_hours_by_months_plan_not_approved_selected_period', {})[
                            month_num] = norm_work_amount

                empl_dict['sawh_hours_plan_approved_selected_period'] = sum(
                    empl_dict.setdefault('sawh_hours_by_months_plan_approved_selected_period', {}).values())
                empl_dict['sawh_hours_plan_not_approved_selected_period'] = sum(
                    empl_dict.setdefault('sawh_hours_by_months_plan_not_approved_selected_period', {}).values())

            work_hours_prev_months = employee_dict.get(
                'fact', {}).get('approved', {}).get('work_hours', {}).get('prev_months', 0)

            for is_fact_key in ['plan', 'fact']:
                for is_approved_key in ['approved', 'not_approved']:
                    overtime = employee_dict.setdefault(
                        is_fact_key, {}
                    ).setdefault(
                        is_approved_key, {}
                    ).setdefault(
                        'overtime', {}
                    )

                    sawh_hours = employee_dict.setdefault(
                        is_fact_key, {}
                    ).setdefault(
                        is_approved_key, {}
                    ).setdefault(
                        'sawh_hours', {}
                    )

                    if is_fact_key == 'plan' and is_approved_key == 'not_approved':
                        for empl_id, empl_dict in employee_dict.get('employments', {}).items():
                            for month_num in acc_period_months:
                                sawh_hours.setdefault('by_months', {})[month_num] = \
                                    sawh_hours.get('by_months', {}).get(month_num, 0) + \
                                    empl_dict.get('sawh_hours_by_months_plan_not_approved', {}).get(month_num, 0)

                            sawh_hours['selected_period'] = sawh_hours.get('selected_period', 0) + \
                                empl_dict.get('sawh_hours_plan_not_approved_selected_period', 0)

                    else:
                        for empl_id, empl_dict in employee_dict.get('employments', {}).items():
                            for month_num in acc_period_months:
                                sawh_hours.setdefault('by_months', {})[month_num] = \
                                    sawh_hours.get('by_months', {}).get(month_num, 0) + \
                                    empl_dict.get('sawh_hours_by_months_plan_approved', {}).get(month_num, 0)

                            sawh_hours['selected_period'] = sawh_hours.get('selected_period', 0) + \
                                empl_dict.get('sawh_hours_plan_approved_selected_period', 0)

                    is_last_month = curr_month == acc_period_dt_to.month
                    if self.network.correct_norm_hours_last_month_acc_period and self.network.accounting_period_length > 1 and is_last_month:
                        acc_period_norm_hours = employee_dict.get(
                            'plan', {}).get('approved', {}).get('norm_hours', {})['acc_period']
                        work_hours_prev_months = employee_dict.get(
                            'plan', {}).get('approved', {}).get('work_hours', {})['prev_months']
                        sawh_hours['curr_month'] = acc_period_norm_hours - work_hours_prev_months
                    else:
                        sawh_hours['curr_month'] = sawh_hours.get('by_months', {}).get(curr_month, 0)

                    work_hours_curr_month = employee_dict.get(
                        is_fact_key).get(is_approved_key).get('work_hours', {}).get('total', 0)
                    work_hours_until_acc_period_end = employee_dict.get(
                        is_fact_key).get(is_approved_key).get('work_hours', {}).get('until_acc_period_end', 0)
                    norm_hours_acc_period = employee_dict.get(
                        is_fact_key).get(is_approved_key).get('norm_hours', {}).get('acc_period', 0)
                    norm_hours_curr_month = employee_dict.get(
                        is_fact_key).get(is_approved_key).get('norm_hours', {}).get('curr_month', 0)
                    norm_hours_prev_months = employee_dict.get(
                        is_fact_key).get(is_approved_key).get('norm_hours', {}).get('prev_months', 0)
                    norm_hours_curr_month_end = employee_dict.get(
                        is_fact_key).get(is_approved_key).get('norm_hours', {}).get('curr_month_end', 0)

                    overtime['acc_period'] = (
                        work_hours_prev_months + work_hours_until_acc_period_end) - norm_hours_acc_period
                    overtime['prev_months'] = work_hours_prev_months - norm_hours_prev_months
                    overtime['curr_month'] = work_hours_curr_month - norm_hours_curr_month
                    overtime['curr_month_end'] = (
                        work_hours_prev_months + work_hours_curr_month) - norm_hours_curr_month_end

        return res
