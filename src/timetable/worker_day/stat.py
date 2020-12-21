import re
from calendar import monthrange
from collections import Counter
from copy import deepcopy
from datetime import timedelta, date
from itertools import groupby

import pandas
from django.db.models import (
    Count, Sum,
    Exists, OuterRef, Subquery,
    F, Q,
    Case, When, Value,
    BooleanField, FloatField,
)
from django.db.models.functions import Extract, Cast, Coalesce, TruncDate
from django.utils.functional import cached_property

from src.base.models import Employment, Shop, ProductionDay, SAWHSettings
from src.forecast.models import PeriodClients
from src.timetable.models import WorkerDay
from src.util.utils import deep_get


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
        has_worker=Case(When(worker_id__isnull=True, then=Value(False)),default=Value(True),output_field=BooleanField()),

        salary=Coalesce(Subquery(emp_subq_shop.values('salary')[:1]), Subquery(emp_subq.values('salary')[:1]), 0),
        is_shop=Exists(emp_subq_shop),
        has_plan=Exists(plan_approved_subq),
    ).filter(
        Q(is_fact=False)|Q(has_plan=True)
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
            'outsource' if has_worker else\
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
            'outsource' if has_worker else\
            'vacancies'

        stat[dt][plan_or_fact]['combined'][shop] = day

    q = [# (metric_name, field_name, Q)
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
            stat[dt][metric_name][day['field']]=day['value']
    return stat


class BaseWorkerParamGetter:
    def __init__(self, stats_getter, dt_from, dt_to, worker_id, worker_days):
        self.stats_getter = stats_getter
        self.dt_from = dt_from
        self.dt_to = dt_to
        self.worker_id = worker_id
        self.worker_days = filter(lambda wd: self.dt_from <= wd.dt <= self.dt_to, worker_days)
        self.res = self.get_initial_res()

    def get_initial_res(self):
        return {}

    def run(self):
        raise NotImplementedError()


class WorkerIterateWorkDaysParamGetter(BaseWorkerParamGetter):
    def handle_worker_day(self, worker_day):
        raise NotImplementedError

    def run(self):
        for worker_day in self.worker_days:
            self.handle_worker_day(worker_day)

        return self.res


class WorkerShopDependingIterateWorkDaysParamGetter(WorkerIterateWorkDaysParamGetter):
    def get_initial_res(self):
        return {
            'total': 0,
            'selected_shop': 0,
            'other_shops': 0,
        }


class WorkerWorkHoursGetter(WorkerShopDependingIterateWorkDaysParamGetter):
    def handle_worker_day(self, worker_day):
        _count_day, work_hours = count_wd_hours(worker_day)
        if work_hours:
            self.res['total'] += work_hours
            if self.stats_getter.shop_id == worker_day.shop_id:
                self.res['selected_shop'] += work_hours
            else:
                self.res['other_shops'] += work_hours


class WorkerWorkDaysGetter(WorkerShopDependingIterateWorkDaysParamGetter):
    def handle_worker_day(self, worker_day):
        count_day, _work_hours = count_wd_hours(worker_day)
        if count_day:
            self.res['total'] += count_day
            if self.stats_getter.shop_id == worker_day.shop_id:
                self.res['selected_shop'] += count_day
            else:
                self.res['other_shops'] += count_day


class WorkerNormHoursGetter(WorkerIterateWorkDaysParamGetter):
    # TODO: сделать возможным настраивать алгоритм расчета нормы ?

    empls_norms = None

    def get_initial_res(self):
        norm_hours = 0
        self.empls_norms = {}
        for empl in self.stats_getter.workers_dict.get(self.worker_id):
            dt_from = max(self.dt_from, empl.dt_hired) if empl.dt_hired else self.dt_from
            dt_to = min(self.dt_to, empl.dt_fired) if empl.dt_fired else self.dt_to
            empl_norm_hours = self.stats_getter.cal.get_prod_cal_days(
                dt_start=dt_from,
                dt_end=dt_to,
                rate=empl.norm_work_hours,
            )
            self.empls_norms[(dt_from, dt_to)] = (empl, empl_norm_hours)
            norm_hours += empl_norm_hours

        return {'value': norm_hours}

    def handle_worker_day(self, worker_day):
        if worker_day.type in [
            WorkerDay.TYPE_VACATION,
            WorkerDay.TYPE_SICK,
            WorkerDay.TYPE_SELF_VACATION,
            WorkerDay.TYPE_MATERNITY,
            WorkerDay.TYPE_MATERNITY_CARE,
        ]:
            for (dt_from, dt_to), (empl, empl_norm_hours) in self.empls_norms.items():
                if dt_from <= worker_day.dt <= dt_to:
                    self.res['value'] -= empl_norm_hours / ((dt_to - dt_from).days + 1)


class WorkerDayTypesCountGetter(BaseWorkerParamGetter):
    def run(self):
        return dict(Counter(wd.type for wd in self.worker_days))


# при добавлении постфикса меняется период за который считается статистика
# без постфикса -- считается за период, который передан
PREV_PERIOD_POSTFIX = 'prev_period'  # период до выбранной даты
CURR_MONTH_POSTFIX = 'curr_month'  # текущий месяц
CURR_MONTH_END_POSTFIX = 'curr_month_end'  # с начала уч. периода до конца текущего месяца
PREV_MONTHS_POSTFIX = 'prev_months'  # прошедшие месяца
ACC_PERIOD_POSTFIX = 'acc_period'  # весь учетный период


COMBINED_GRAPHS_MAPPING = {
    ('fact', 'approved'): ('plan', 'approved'),
    ('fact', 'not_approved'): ('plan', 'approved'),
    ('fact', 'combined'): ('plan', 'approved'),
}

worker_params_getters = (
    # рабочих дней
    ('work_days', {'cls': WorkerWorkDaysGetter},),  # Рабочих дней за выбранный период

    # рабочих часов
    ('work_hours', {'cls': WorkerWorkHoursGetter},),
    (f'work_hours_{CURR_MONTH_POSTFIX}', {'cls': WorkerWorkHoursGetter},),
    (f'work_hours_{CURR_MONTH_END_POSTFIX}', {'cls': WorkerWorkHoursGetter},),
    (f'work_hours_{PREV_MONTHS_POSTFIX}', {'cls': WorkerWorkHoursGetter},),
    (f'work_hours_{PREV_PERIOD_POSTFIX}', {'cls': WorkerWorkHoursGetter},),
    (f'work_hours_{ACC_PERIOD_POSTFIX}', {'cls': WorkerWorkHoursGetter},),

    # количество типов дней
    ('day_type', {'cls': WorkerDayTypesCountGetter},),

    # норма часов
    (f'norm_hours_{CURR_MONTH_POSTFIX}', {'cls': WorkerNormHoursGetter, 'res_mapping': COMBINED_GRAPHS_MAPPING},),
    (f'norm_hours_{PREV_MONTHS_POSTFIX}', {'cls': WorkerNormHoursGetter, 'res_mapping': COMBINED_GRAPHS_MAPPING},),
    (f'norm_hours_{CURR_MONTH_END_POSTFIX}', {'cls': WorkerNormHoursGetter, 'res_mapping': COMBINED_GRAPHS_MAPPING},),
    (f'norm_hours_{ACC_PERIOD_POSTFIX}', {'cls': WorkerNormHoursGetter, 'res_mapping': COMBINED_GRAPHS_MAPPING},),

    # переработки
    (f'overtime_{CURR_MONTH_POSTFIX}', {
        'calc_str': f'{{work_hours_{CURR_MONTH_POSTFIX}|total}}-{{norm_hours_{CURR_MONTH_POSTFIX}|value}}',
    },),
    (f'overtime_{CURR_MONTH_END_POSTFIX}', {
        'calc_str': f'{{work_hours_{CURR_MONTH_END_POSTFIX}|total}}-{{norm_hours_{CURR_MONTH_END_POSTFIX}|value}}',
    },),
    (f'overtime_{PREV_MONTHS_POSTFIX}', {
        'calc_str': f'{{work_hours_{PREV_MONTHS_POSTFIX}|total}}-{{norm_hours_{PREV_MONTHS_POSTFIX}|value}}',
    },),
    (f'overtime_{ACC_PERIOD_POSTFIX}', {
        'calc_str': f'{{work_hours_{ACC_PERIOD_POSTFIX}|total}}-{{norm_hours_{ACC_PERIOD_POSTFIX}|value}}',
    },),
)
worker_params_getters_map = dict(worker_params_getters)


class WorkersStatsGetter:
    def __init__(self, dt_from, dt_to, shop_id, worker_id=None, worker_id__in=None):
        self.dt_from = dt_from
        self.dt_to = dt_to
        self.worker_id = worker_id
        self.worker_id__in = worker_id__in
        self.shop_id = shop_id
        self.year = dt_from.year
        self.month = dt_from.month
        self.res = {}

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
            shop_id=self.shop_id,
        )
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

    @cached_property
    def prod_cal_hours_by_months(self):
        return ProductionDay.get_norm_work_hours(self.shop.region_id, self.year)

    @cached_property
    def cal(self):
        dt_start, dt_end = self.acc_period_range
        return CalendarPaidDays(dt_start, dt_end, self.shop.region_id)

    def get_worker_day_qs(self):
        dt_from, dt_to = self.acc_period_range
        return WorkerDay.objects.filter(
            dt__gte=dt_from,
            dt__lte=dt_to,
            worker_id__in=self.workers_dict.keys(),
            type__in=WorkerDay.TYPES_USED,
        ).exclude(
            Q(type__in=WorkerDay.TYPES_WITH_TM_RANGE) &
            Q(
                Q(dttm_work_start__isnull=True) |
                Q(dttm_work_end__isnull=True)
            )
        ).select_related(
            'employment',
        ).order_by(  # порядок важен для группировки дней
            'worker_id',
            'is_fact',
            'dt',
            'is_approved',
        )

    def get_worker_param_getter_kwargs(self, param_name, worker_id, worker_days):
        kwargs = {
            'dt_from': self.dt_from,
            'dt_to': self.dt_to,
            'stats_getter': self,
            'worker_id': worker_id,
            'worker_days': worker_days,
        }

        if param_name.endswith(PREV_PERIOD_POSTFIX):
            kwargs['dt_from'], kwargs['dt_to'] = self.prev_range
        elif param_name.endswith(CURR_MONTH_POSTFIX):
            kwargs['dt_from'], kwargs['dt_to'] = self.curr_month_range
        elif param_name.endswith(CURR_MONTH_END_POSTFIX):
            kwargs['dt_from'], kwargs['dt_to'] = self.curr_month_end_range
        elif param_name.endswith(PREV_MONTHS_POSTFIX):
            kwargs['dt_from'], kwargs['dt_to'] = self.prev_months_range
        elif param_name.endswith(ACC_PERIOD_POSTFIX):
            kwargs['dt_from'], kwargs['dt_to'] = self.acc_period_range

        return kwargs

    def calc_worker_param(self, worker_id, initial_plan_or_fact, initial_graph_type, name):
        options = worker_params_getters_map.get(name)
        cls = options.get('cls', {})
        calc_str = options.get('calc_str', '')
        res_mapping = options.get('res_mapping', {})

        plan_or_fact, graph_type = initial_plan_or_fact, initial_graph_type
        replaced_plan_or_fact, replaced_graph_type = None, None

        if res_mapping.get((initial_plan_or_fact, initial_graph_type)):
            plan_or_fact, graph_type = res_mapping.get((initial_plan_or_fact, initial_graph_type))
            replaced_plan_or_fact, replaced_graph_type = initial_plan_or_fact, initial_graph_type

        res = self.res.get(str(worker_id), {}).get(plan_or_fact, {}).get(graph_type, {}).get(name, {})
        data = {}
        if res:
            data = res
            if replaced_plan_or_fact and replaced_graph_type:
                self.res.setdefault(str(worker_id), {}).setdefault(replaced_plan_or_fact, {}).setdefault(
                    replaced_graph_type, {}).setdefault(name, {}).update(data)
        elif cls:
            worker_days = self.wdays_dict.get(str(worker_id), {}).get(plan_or_fact, {}).get(graph_type, [])
            data = cls(
                **self.get_worker_param_getter_kwargs(
                    param_name=name, worker_id=worker_id, worker_days=worker_days)).run()
            self.res.setdefault(str(worker_id), {}).setdefault(
                plan_or_fact, {}).setdefault(graph_type, {}).setdefault(name, {}).update(data)
        elif calc_str:
            calc_names = re.findall(r'[\w|]+', calc_str)
            calc_data = {}
            for calc_params in calc_names:
                calc_name, calc_path = calc_params.split('|')
                calc_data[calc_params] = deep_get(self.calc_worker_param(
                    worker_id, initial_plan_or_fact, initial_graph_type, calc_name), calc_path)
            data = {'value': eval(calc_str.format(**calc_data))}
            self.res.setdefault(str(worker_id), {}).setdefault(
                plan_or_fact, {}).setdefault(graph_type, {}).setdefault(name, {}).update(data)

        return data

    def calc_worker_params(self, worker_id, initial_plan_or_fact, initial_graph_type):
        for name, _options in worker_params_getters:
            self.calc_worker_param(worker_id, initial_plan_or_fact, initial_graph_type, name)

    def get_wdays_for_graph_types(self, worker_days):
        dt = worker_days[0].dt
        wdays_approved = []
        wdays_not_approved = []
        wdays_combined = []
        combined_added = False
        for wd in worker_days:
            if wd.is_approved:
                wdays_approved.append(wd)
            else:
                wdays_not_approved.append(wd)

            if wd.dt != dt:
                dt = wd.dt
                combined_added = False

            if not combined_added:
                wdays_combined.append(wd)
                combined_added = True

        return {
            'approved': wdays_approved,
            'not_approved': wdays_not_approved,
            'combined': wdays_combined,
        }

    @staticmethod
    def _init_empty(empty_val_callable=dict):
        return {
            'approved': empty_val_callable(),
            'not_approved': empty_val_callable(),
            'combined': empty_val_callable(),
        }

    def prepare_wdays_dict(self, worker_days):
        grouped_worker_days = {k: list(g) for k, g in
                               groupby(worker_days, lambda wd: (wd.worker_id, wd.is_fact))}
        worker_days_dict = {}
        for (worker_id, is_fact), worker_days in grouped_worker_days.items():
            worker_days_dict.setdefault(
                str(worker_id), {'plan': self._init_empty(list), 'fact': self._init_empty(list)})[
                'fact' if is_fact else 'plan'] = self.get_wdays_for_graph_types(worker_days)

        return worker_days_dict

    def run(self):
        acc_period_worker_days = list(self.get_worker_day_qs())
        if not len(acc_period_worker_days):
            return self.res

        self.wdays_dict = self.prepare_wdays_dict(acc_period_worker_days)

        for worker_id in self.workers_dict.keys():
            for plan_or_fact in ['plan', 'fact']:
                for graph_type in ['approved', 'combined', 'not_approved']:
                    self.calc_worker_params(worker_id, plan_or_fact, graph_type)

        return self.res


def count_wd_hours(wd):
    if wd.work_hours > timedelta(0):
        return 1, wd.work_hours.seconds / 3600

    return 0, 0


class CalendarPaidDays:
    def __init__(self, dt_start, dt_end, region_id):
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

    def get_prod_cal_days(self, dt_start, dt_end, rate=100):
        return self.calendar_days.loc[(
                (self.calendar_days.index >= dt_start)
                & (self.calendar_days.index <= dt_end)
        )].hours.sum() * rate / 100
