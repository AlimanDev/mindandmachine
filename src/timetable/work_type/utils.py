import datetime

import numpy as np
from django.db.models import Q, F, Sum
from django.utils.functional import cached_property
from rest_framework.exceptions import ValidationError

from src.base.models import (
    Shop,
    Employment,
)
from src.forecast.models import (
    PeriodClients,
)
from src.timetable.models import ProdCal
from src.timetable.models import (
    WorkerDay,
    WorkType,
)
from src.util.models_converter import Converter

MINUTES_IN_DAY = 24 * 60


class ShopEfficiencyGetterError(ValidationError):
    pass


class ShopEfficiencyGetter:
    def __init__(self, shop_id, from_dt, to_dt, graph_type='plan_approved', work_type_ids: list = None,
                 consider_vacancies=False, efficiency=True, indicators=False, **kwargs):
        self.shop_id = shop_id
        self.dt_from = from_dt
        self.dt_to = to_dt + datetime.timedelta(days=1)  # To include last day in "x < to_dt" conds
        self.graph_type = graph_type
        self.work_type_ids = work_type_ids
        self.consider_vacancies = consider_vacancies  # для обратной совместимости
        self.efficiency = efficiency
        self.indicators = indicators
        self.lambda_index_periodclients = lambda x: [self._dttm2index(self.dt_from, x.dttm_forecast)]
        self.lambda_add_periodclients = lambda x: x.need_workers
        self.lambda_index_wdays = lambda x: list(range(
            self._dttm2index(self.dt_from, x.dttm_work_start),
            self._dttm2index(self.dt_from, x.dttm_work_end),
        ))
        self.lambda_add_wdays = lambda x: x.work_part
        self.lambda_index_work_hours = lambda x: [self._dt2index(self.dt_from, x.dt)]
        self.lambda_add_work_hours = lambda x: (x.work_hours.total_seconds()) / 3600
        self.lambda_index_work_days = lambda x: [self._dt2index(self.dt_from, x.dt)]
        self.lambda_add_work_days = lambda x: 1
        self.lambda_index_income = lambda x: [self._dt2index(self.dt_from, x.dttm_forecast.date())]
        self.lambda_add_income = lambda x: x.value
        self.kwargs = kwargs
        self.response = {}

    def _dttm2index(self, dt_init, dttm):
        days = (dttm.date() - dt_init).days
        return days * self.periods_in_day + (dttm.hour * 60 + dttm.minute) // self.period_length_in_minutes

    def _dt2index(self, dt_init, dt):
        days = (dt - dt_init).days
        return days

    def _fill_array(self, array, db_list, lambda_get_indexes, lambda_add):
        arr_sz = array.size
        for db_model in db_list:
            # период может быть до 12 ночи, а смена с 10 до 8 утра следующего дня и поэтому выходим за границы
            indexes = [ind for ind in lambda_get_indexes(db_model) if ind < arr_sz]
            array[indexes] += lambda_add(db_model)

    @cached_property
    def shop(self):
        return Shop.objects.all().select_related('settings', 'network').get(id=self.shop_id)

    @cached_property
    def absenteeism_coef(self):
        absenteeism_coef = 1
        if self.shop.settings:
            absenteeism_coef += self.shop.settings.absenteeism / 100
        return absenteeism_coef

    @cached_property
    def period_length_in_minutes(self):
        return self.shop.forecast_step_minutes.hour * 60 + self.shop.forecast_step_minutes.minute

    @cached_property
    def periods_in_day(self):
        return MINUTES_IN_DAY // self.period_length_in_minutes

    @cached_property
    def dttms(self):
        dttms = [
            datetime.datetime.combine(self.dt_from + datetime.timedelta(days=day), datetime.time(
                hour=period * self.period_length_in_minutes // 60,
                minute=period * self.period_length_in_minutes % 60))
            for day in range((self.dt_to - self.dt_from).days)
            for period in range(self.periods_in_day)
        ]
        return dttms

    def _check_and_init_work_types(self):
        work_types = WorkType.objects.filter(shop_id=self.shop_id).order_by('id')
        if self.work_type_ids:
            work_types = work_types.filter(id__in=self.work_type_ids)
            if work_types.count() != len(self.work_type_ids):
                raise ShopEfficiencyGetterError('bad work_type_ids')

        self.work_types = {wt.id: wt for wt in work_types}

    def _get_predict_needs_qs(self):
        return PeriodClients.objects.shop_times_filter(self.shop, weekday=True).annotate(
            need_workers=F('value'),
        ).select_related('operation_type').filter(
            dttm_forecast__gte=self.dt_from,
            dttm_forecast__lte=self.dt_to,
            operation_type__work_type_id__in=self.work_types.keys(),
            operation_type__dttm_deleted__isnull=True,
        )

    def _get_wdays_qs(self, consider_vacancies=False):
        base_wd_q = Q(
            Q(employment__dt_fired__gte=self.dt_from) &
            Q(dt__lte=F('employment__dt_fired')) |
            Q(employment__dt_fired__isnull=True),
            Q(employment__dt_hired__lte=self.dt_to) &
            Q(dt__gte=F('employment__dt_hired')) |
            Q(employment__dt_hired__isnull=True),
            canceled=False,
            dt__gte=self.dt_from,
            dt__lte=self.dt_to,
        )
        if not consider_vacancies:
            base_wd_q &= Q(employee__isnull=False)

        qs = WorkerDay.objects.filter(base_wd_q)

        if self.graph_type == 'plan_edit':
            qs = qs.get_plan_not_approved()
        elif self.graph_type == 'fact_approved':
            qs = qs.get_fact_approved()
        elif self.graph_type == 'fact_edit':
            qs = qs.get_fact_not_approved()
        else:
            qs = qs.get_plan_approved()

        qs = qs.filter(
            type__in=WorkerDay.TYPES_PAID,
            worker_day_details__work_type_id__in=self.work_types.keys(),
        ).exclude(
            Q(dttm_work_start__isnull=True) | Q(dttm_work_end__isnull=True),
        ).annotate(work_part=F('worker_day_details__work_part')).distinct()

        return qs

    def _get_income_qs(self):
        income_code = self.shop.network.settings_values_prop.get('income_code', None)
        if not income_code:
            PeriodClients.objects.none()

        return PeriodClients.objects.filter(
            type=PeriodClients.FACT_TYPE,
            operation_type__shop=self.shop,
            operation_type__operation_type_name__code=income_code,
            dttm_forecast__gte=self.dt_from,
            dttm_forecast__lte=self.dt_to,
            operation_type__dttm_deleted__isnull=True,
        )

    def _init_arrays(self):
        consider_vacancy_map_wdays = {
            True: list(self._get_wdays_qs(consider_vacancies=True)),
            False: list(self._get_wdays_qs(consider_vacancies=False)),
        }
        self.predict_needs_array = np.zeros(len(self.dttms))
        self._fill_array(
            self.predict_needs_array,
            list(self._get_predict_needs_qs().filter(type=PeriodClients.LONG_FORECASE_TYPE)),
            self.lambda_index_periodclients,
            self.lambda_add_periodclients,
        )
        self.wdays_array = np.zeros(len(self.dttms))
        self._fill_array(
            self.wdays_array,
            consider_vacancy_map_wdays.get(self.consider_vacancies),
            self.lambda_index_wdays,
            self.lambda_add_wdays,
        )
        self.wdays_with_open_vacancies_array = np.zeros(len(self.dttms))
        self._fill_array(
            self.wdays_with_open_vacancies_array,
            consider_vacancy_map_wdays.get(True),
            self.lambda_index_wdays,
            self.lambda_add_wdays,
        )
        self.work_hours_array = np.zeros(len(self.dttms))
        self._fill_array(
            self.work_hours_array,
            consider_vacancy_map_wdays.get(False),
            self.lambda_index_work_hours,
            self.lambda_add_work_hours,
        )
        self.work_days_array = np.zeros(len(self.dttms))
        self._fill_array(
            self.work_days_array,
            consider_vacancy_map_wdays.get(False),
            self.lambda_index_work_days,
            self.lambda_add_work_days,
        )
        self.income_array = np.zeros(len(self.dttms))
        self._fill_array(
            self.income_array,
            list(self._get_income_qs()),
            self.lambda_index_income,
            self.lambda_add_income,
        )

    def _calc_efficiency(self):
        day_stats = {}

        dts_for_day_stats = [
            self.dt_from + datetime.timedelta(days=day)
            for day in range((self.dt_to - self.dt_from).days)
        ]
        dts_for_day_stats_len = len(dts_for_day_stats)

        wdays_array_daily = self.wdays_array.reshape(dts_for_day_stats_len, self.periods_in_day)
        wdays_with_open_vacancies_array_daily = self.wdays_with_open_vacancies_array.reshape(
            dts_for_day_stats_len, self.periods_in_day)
        predict_needs_array_daily = self.predict_needs_array.reshape(dts_for_day_stats_len, self.periods_in_day)

        for i, dt in enumerate(dts_for_day_stats):
            dt_converted = Converter.convert_date(dt)

            wdays_array_for_dt = wdays_array_daily[i]
            wdays_with_open_vacancies_array_for_dt = wdays_with_open_vacancies_array_daily[i]
            predict_needs_for_dt = predict_needs_array_daily[i]
            work_hours_for_dt = self.work_hours_array[i]
            work_days_for_dt = self.work_days_array[i]
            income_for_dt = self.income_array[i]

            covering = np.nan_to_num(
                np.minimum(predict_needs_for_dt, wdays_array_for_dt).sum() / predict_needs_for_dt.sum())
            deadtime = np.nan_to_num(
                np.maximum(wdays_array_for_dt - predict_needs_for_dt, 0).sum() / wdays_array_for_dt.sum())
            predict_hours = int((predict_needs_for_dt * self.period_length_in_minutes / 60).sum())
            graph_hours = int((wdays_array_for_dt * self.period_length_in_minutes / 60).sum())
            graph_hours_with_open_vacancies = int(
                (wdays_with_open_vacancies_array_for_dt * self.period_length_in_minutes / 60).sum())
            work_hours = np.nan_to_num(work_hours_for_dt).sum()
            work_days = np.nan_to_num(work_days_for_dt).sum()
            income = np.nan_to_num(income_for_dt).sum()

            day_stats.setdefault('covering', {})[dt_converted] = covering
            day_stats.setdefault('deadtime', {})[dt_converted] = deadtime
            day_stats.setdefault('predict_hours', {})[dt_converted] = predict_hours
            day_stats.setdefault('graph_hours', {})[dt_converted] = graph_hours
            day_stats.setdefault('graph_hours_with_open_vacancies', {})[dt_converted] = graph_hours_with_open_vacancies
            day_stats.setdefault('work_hours', {})[dt_converted] = work_hours
            day_stats.setdefault('work_days', {})[dt_converted] = work_days
            day_stats.setdefault('income', {})[dt_converted] = income
            day_stats.setdefault('perfomance', {})[dt_converted] = np.nan_to_num(income / work_hours)

        real_cashiers = []
        predict_cashier_needs = []
        lack_of_cashiers_on_period = []
        for index, dttm in enumerate(self.dttms):
            dttm_converted = Converter.convert_datetime(dttm)
            real_cashiers.append({'dttm': dttm_converted, 'amount': self.wdays_array[index]})
            predict_cashier_needs.append({'dttm': dttm_converted, 'amount': self.predict_needs_array[index]})
            lack_of_cashiers_on_period.append({
                'dttm': dttm_converted,
                'lack_of_cashiers': max(0, self.predict_needs_array[index] - self.wdays_array[index])
            })

        self.response.update({
            'period_step': self.period_length_in_minutes,
            'tt_periods': {
                'real_cashiers': real_cashiers,
                'predict_cashier_needs': predict_cashier_needs,
            },
            'day_stats': day_stats,
            'lack_of_cashiers_on_period': lack_of_cashiers_on_period
        })

    def _calc_indicators(self):
        active_shop_empls_for_period = Employment.objects.get_active(
            network_id=self.shop.network_id,
            dt_from=self.dt_from,
            dt_to=self.dt_to,
            shop_id=self.shop_id,
        )
        # ФОТ считаем как: часы производственные календарь * кол-во сотрудников с учетом их ставок.
        fot = ProdCal.objects.filter(
            employee__in=active_shop_empls_for_period.values_list('employee_id', flat=True),
        ).aggregate(
            norm_hours_sum=Sum('norm_hours')
        )['norm_hours_sum']
        covering = round(100 * np.nan_to_num(
            np.minimum(self.predict_needs_array, self.wdays_array).sum() / self.predict_needs_array.sum()), 1)
        deadtime = round(100 * np.nan_to_num(
            np.maximum(self.wdays_array - self.predict_needs_array, 0).sum() / (self.wdays_array.sum())), 1)

        self.response.update({
            'indicators': {
                'deadtime': deadtime,
                'covering': covering,
                'fot': fot,
                'predict_needs': self.predict_needs_array.sum(),
            },
        })

    def get(self):
        self._check_and_init_work_types()
        self._init_arrays()

        if self.efficiency:
            self._calc_efficiency()

        if self.indicators:
            self._calc_indicators()

        return self.response
