import datetime

import pandas as pd
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import transaction
from django.db.models import (
    Q
)
from django.utils import timezone

from src.base.models import Employee
from .dividers import FISCAL_SHEET_DIVIDERS_MAPPING
from ..models import WorkerDay, Timesheet


def _get_calc_periods(dt_fired=None):
    dt_fired = dt_fired or datetime.date(3999, 12, 31)
    periods = []
    dt_now = timezone.now().date()

    if dt_now.day <= 4:
        dt_start = (dt_now - relativedelta(months=1)).replace(day=1)
        dt_end = min(dt_fired, (dt_start + relativedelta(months=1)).replace(day=1) - datetime.timedelta(days=1))
        periods.append((dt_start, dt_end), )

    dt_start = dt_now.replace(day=1)
    dt_end = min(dt_fired, (dt_now + relativedelta(months=1)).replace(day=1) - datetime.timedelta(days=1))
    periods.append((dt_start, dt_end), )

    return periods


class TimesheetCalculator:
    def __init__(self, employee: Employee):
        self.employee = employee

    def _get_timesheet_wdays_qs(self, employee, dt_start, dt_end):
        return WorkerDay.objects.get_tabel(
            Q(is_fact=False) | Q(
                is_fact=True,
                type__in=WorkerDay.TYPES_WITH_TM_RANGE,
                dttm_work_start__isnull=False, dttm_work_end__isnull=False,
                work_hours__gte=datetime.timedelta(0),
            ),
            employee=employee,
            dt__gte=dt_start, dt__lte=dt_end,
        ).only(
            'employee_id',
            'dt',
            'type',
            'work_hours',
            'dttm_work_start_tabel',
            'dttm_work_end_tabel',
            'shop__network__settings_values',
        )

    def _get_empl_key(self, employee_id, dt):
        return dt

    def _get_fact_timesheet_data(self, dt_start, dt_end):
        wdays_qs = self._get_timesheet_wdays_qs(self.employee, dt_start, dt_end)
        fact_timesheet_dict = {}
        for worker_day in wdays_qs:
            wd_dict = {
                'employee_id': self.employee.id,
                'dt': worker_day.dt,
                'shop_id': worker_day.shop_id,
                'fact_timesheet_type': worker_day.type,
                'fact_timesheet_source': Timesheet.SOURCE_TYPE_FACT if worker_day.is_fact else Timesheet.SOURCE_TYPE_PLAN,
            }
            if worker_day.type in WorkerDay.TYPES_WITH_TM_RANGE:
                total_hours, day_hours, night_hours = worker_day.calc_day_and_night_work_hours()
                wd_dict['fact_timesheet_dttm_work_start'] = worker_day.dttm_work_start_tabel
                wd_dict['fact_timesheet_dttm_work_end'] = worker_day.dttm_work_end_tabel
                wd_dict['fact_timesheet_total_hours'] = total_hours
                wd_dict['fact_timesheet_day_hours'] = day_hours
                wd_dict['fact_timesheet_night_hours'] = night_hours
            fact_timesheet_dict[self._get_empl_key(self.employee.id, worker_day.dt)] = wd_dict

        plan_wdays_dict = {f'{wd.employee_id}_{wd.dt}': wd for wd in WorkerDay.objects.filter(
            employee=self.employee,
            dt__gte=dt_start,
            dt__lte=dt_end,
            is_approved=True,
            is_fact=False,
        ).exclude(
            type=WorkerDay.TYPE_EMPTY,
        ).select_related(
            'employee__user',
            'shop__network',
        )}
        dt_now = timezone.now().date()
        for dt in pd.date_range(dt_start, dt_end).date:
            empl_dt_key = self._get_empl_key(self.employee.id, dt)
            resp_wd = fact_timesheet_dict.get(empl_dt_key)
            if resp_wd:  # если есть ответ для сотрудника на конкретный день, то пропускаем
                continue

            plan_wd = plan_wdays_dict.get(empl_dt_key)

            # Если нет ни плана ни факта
            if not plan_wd:
                d = {
                    'employee_id': self.employee.id,
                    'dt': dt,
                    'shop_id': None,
                    'fact_timesheet_type': WorkerDay.TYPE_HOLIDAY,
                    'fact_timesheet_source': Timesheet.SOURCE_TYPE_SYSTEM,
                }
                fact_timesheet_dict[empl_dt_key] = d
                continue

            # при отсутствии факта но при наличии плана
            # для дней в прошлом ставим прогул, в остальных случаях берем день из плана
            if plan_wd:
                day_in_past = dt < dt_now
                d = {
                    'employee_id': self.employee.id,
                    'dt': dt,
                    'shop_id': None if day_in_past else plan_wd.shop_id,
                    'fact_timesheet_type': WorkerDay.TYPE_ABSENSE if day_in_past else plan_wd.type,
                    'fact_timesheet_source': Timesheet.SOURCE_TYPE_SYSTEM if day_in_past else Timesheet.SOURCE_TYPE_PLAN,
                }
                if not day_in_past:
                    total_hours, day_hours, night_hours = plan_wd.calc_day_and_night_work_hours()
                    d['fact_timesheet_dttm_work_start'] = plan_wd.dttm_work_start_tabel
                    d['fact_timesheet_dttm_work_end'] = plan_wd.dttm_work_end_tabel
                    d['fact_timesheet_total_hours'] = total_hours
                    d['fact_timesheet_day_hours'] = day_hours
                    d['fact_timesheet_night_hours'] = night_hours
                fact_timesheet_dict[empl_dt_key] = d

        return fact_timesheet_dict

    def _calc(self, dt_start, dt_end):
        fiscal_sheet_dict = self._get_fact_timesheet_data(dt_start, dt_end)
        if settings.FISCAL_SHEET_DIVIDER_ALIAS:
            fiscal_sheet_divider_cls = FISCAL_SHEET_DIVIDERS_MAPPING.get(settings.FISCAL_SHEET_DIVIDER_ALIAS)
            if fiscal_sheet_divider_cls:
                fiscal_sheet_dict = fiscal_sheet_divider_cls(
                    employee=self.employee,
                    fiscal_sheet_dict=fiscal_sheet_dict,
                    dt_start=dt_start, dt_end=dt_end,
                ).divide()

        with transaction.atomic():
            Timesheet.objects.filter(
                employee=self.employee,
                dt__gte=dt_start,
                dt__lte=dt_end,
            ).delete()
            Timesheet.objects.bulk_create(Timesheet(**d) for d in fiscal_sheet_dict.values())

    def calc(self):
        periods = _get_calc_periods(dt_fired=getattr(self.employee, 'dt_fired', None))
        for period in periods:
            self._calc(dt_start=period[0], dt_end=period[1])
