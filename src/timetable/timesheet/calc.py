import datetime
import logging

import pandas as pd
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from src.base.models import Employee
from .common import _create_timesheet_items
from .dividers import FISCAL_SHEET_DIVIDERS_MAPPING
from ..models import WorkerDay, TimesheetItem, WorkerDayType

logger = logging.getLogger('calc_timesheets')


def _get_calc_periods(dt_hired=None, dt_fired=None, dt_from=None, dt_to=None):
    dt_hired = dt_hired or datetime.date.min
    dt_fired = dt_fired or datetime.date.max

    periods = []
    if (dt_from is None and dt_to is None):
        dt_now = timezone.now().date()

        if dt_now.day <= 4:
            prev_month_start = (dt_now - relativedelta(months=1)).replace(day=1)
            prev_month_end = (prev_month_start + relativedelta(months=1)).replace(day=1) - datetime.timedelta(days=1)
            dt_start = max(dt_hired, prev_month_start)
            dt_end = min(dt_fired, prev_month_end)
            if dt_start <= dt_end:
                periods.append((dt_start, dt_end), )

        curr_month_start = dt_now.replace(day=1)
        curr_month_end = (dt_now + relativedelta(months=1)).replace(day=1) - datetime.timedelta(days=1)
        dt_start = max(dt_hired, curr_month_start)
        dt_end = min(dt_fired, curr_month_end)
        if dt_start <= dt_end:
            periods.append((dt_start, dt_end), )
        periods.append((dt_start, dt_end), )
    else:
        dt_start = max(dt_hired, dt_from)
        dt_end = min(dt_fired, dt_to)
        if dt_start < dt_end:
            periods.append((dt_start, dt_end))

    return periods


class TimesheetCalculator:
    def __init__(self, employee: Employee, dt_from=None, dt_to=None, wd_types_dict=None):
        self.employee = employee
        self.dt_from = dt_from
        self.dt_to = dt_to
        self.wd_types_dict = wd_types_dict or WorkerDayType.get_wd_types_dict()

    def _get_timesheet_wdays_qs(self, employee, dt_start, dt_end):
        return WorkerDay.objects.get_tabel(
            employee=employee,
            dt__gte=dt_start,
            dt__lte=dt_end,
        ).only(
            'employee_id',
            'dt',
            'type',
            'type__is_dayoff',
            'work_hours',
            'dttm_work_start_tabel',
            'dttm_work_end_tabel',
        ).prefetch_related(
            'work_types',
        ).order_by(
            'employee_id',
            'dt',
            'dttm_work_start_tabel',
            'dttm_work_end_tabel',
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
                'shop_id': worker_day.shop_id if not worker_day.type.is_dayoff else None,
                # TODO: замена типа работ на должность
                'position_id': worker_day.employment.position_id if not worker_day.type.is_dayoff else None,
                # TODO: поддержка нескольких типов работ?
                'work_type_name_id': worker_day.work_types.first().work_type_name_id if worker_day.type_id == WorkerDay.TYPE_WORKDAY else None,
                'fact_timesheet_type_id': worker_day.type_id,
                'fact_timesheet_source': TimesheetItem.SOURCE_TYPE_FACT if worker_day.is_fact else TimesheetItem.SOURCE_TYPE_PLAN,
            }
            if not worker_day.type.is_dayoff:
                total_hours, day_hours, night_hours = worker_day.calc_day_and_night_work_hours()
                wd_dict['fact_timesheet_dttm_work_start'] = worker_day.dttm_work_start_tabel
                wd_dict['fact_timesheet_dttm_work_end'] = worker_day.dttm_work_end_tabel
                wd_dict['fact_timesheet_total_hours'] = total_hours
                wd_dict['fact_timesheet_day_hours'] = day_hours
                wd_dict['fact_timesheet_night_hours'] = night_hours
            fact_timesheet_dict.setdefault(self._get_empl_key(self.employee.id, worker_day.dt), []).append(wd_dict)

        plan_wdays_qs = WorkerDay.objects.filter(
            employee=self.employee,
            dt__gte=dt_start,
            dt__lte=dt_end,
            is_approved=True,
            is_fact=False,
        ).exclude(
            type_id=WorkerDay.TYPE_EMPTY,
        ).select_related(
            'employee__user__network',
            'shop__network',
        ).prefetch_related(
            'work_types',
        )
        plan_wdays_dict = {}
        for wd in plan_wdays_qs:
            plan_wdays_dict.setdefault(self._get_empl_key(wd.employee_id, wd.dt), []).append(wd)
        dt_now = timezone.now().date()
        for dt in pd.date_range(dt_start, dt_end).date:
            empl_dt_key = self._get_empl_key(self.employee.id, dt)
            resp_wd = fact_timesheet_dict.get(empl_dt_key)
            if resp_wd:  # если есть ответ для сотрудника на конкретный день, то пропускаем
                continue

            plan_wd_list = plan_wdays_dict.get(empl_dt_key)

            # Если нет ни плана ни факта
            if not plan_wd_list:
                d = {
                    'employee_id': self.employee.id,
                    'dt': dt,
                    'shop_id': None,
                    'fact_timesheet_type_id': WorkerDay.TYPE_HOLIDAY,
                    'fact_timesheet_source': TimesheetItem.SOURCE_TYPE_SYSTEM,
                }
                fact_timesheet_dict.setdefault(empl_dt_key, []).append(d)
                continue

            # при отсутствии факта но при наличии плана
            # для дней в прошлом ставим прогул, в остальных случаях берем день из плана
            if plan_wd_list:
                for plan_wd in plan_wd_list:
                    day_in_past = dt < dt_now
                    d = {
                        'employee_id': self.employee.id,
                        'dt': dt,
                        'shop_id': None if day_in_past else plan_wd.shop_id,
                        'position_id': plan_wd.employment.position_id if (not day_in_past and not plan_wd.is_dayoff) else None,
                        # TODO: замена типа работ на должность
                        'work_type_name_id': plan_wd.work_types.first().work_type_name_id if (not day_in_past and plan_wd.type_id == WorkerDay.TYPE_WORKDAY) else None,
                        # TODO: поддержка нескольких типов работ?
                        'fact_timesheet_type_id': WorkerDay.TYPE_ABSENSE if day_in_past else plan_wd.type_id,
                        'fact_timesheet_source': TimesheetItem.SOURCE_TYPE_SYSTEM if day_in_past else TimesheetItem.SOURCE_TYPE_PLAN,
                    }
                    if not day_in_past:
                        total_hours, day_hours, night_hours = plan_wd.calc_day_and_night_work_hours()
                        d['fact_timesheet_dttm_work_start'] = plan_wd.dttm_work_start_tabel
                        d['fact_timesheet_dttm_work_end'] = plan_wd.dttm_work_end_tabel
                        d['fact_timesheet_total_hours'] = total_hours
                        d['fact_timesheet_day_hours'] = day_hours
                        d['fact_timesheet_night_hours'] = night_hours
                    fact_timesheet_dict.setdefault(empl_dt_key, []).append(d)

                    # если день в прошлом, то ставим только 1 прогул, независимо от того сколько workerday в плане
                    if day_in_past:
                        break

        return fact_timesheet_dict

    def _calc(self, dt_start, dt_end):
        logger.info(f'start receiving fact timesheet')
        fact_timesheet_data = self._get_fact_timesheet_data(dt_start, dt_end)

        with transaction.atomic():
            TimesheetItem.objects.filter(
                employee=self.employee,
                dt__gte=dt_start,
                dt__lte=dt_end,
            ).delete()
            _create_timesheet_items(
                timesheet_dict=fact_timesheet_data,
                timesheet_type_key='fact',
                day_hours_field='fact_timesheet_day_hours',
                night_hours_field='fact_timesheet_night_hours',
                timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
                create_timesheet_item_cond_func=lambda i: i.get('fact_timesheet_type_id') is not None
            )

            logger.info(f'fact timesheet received')
            if settings.FISCAL_SHEET_DIVIDER_ALIAS:
                fiscal_sheet_divider_cls = FISCAL_SHEET_DIVIDERS_MAPPING.get(settings.FISCAL_SHEET_DIVIDER_ALIAS)
                if fiscal_sheet_divider_cls:
                    fiscal_sheet_divider_cls(
                        employee=self.employee,
                        fact_timesheet_data=fact_timesheet_data,
                        dt_start=dt_start, dt_end=dt_end,
                        wd_types_dict=self.wd_types_dict,
                    ).divide()

    def calc(self):
        logger.info(
            f'start timesheet calc for employee with id={self.employee.id} tabel_code={self.employee.tabel_code}')

        periods = _get_calc_periods(
            dt_hired=getattr(self.employee, 'dt_hired', None),
            dt_fired=getattr(self.employee, 'dt_fired', None),
            dt_from=self.dt_from,
            dt_to=self.dt_to,
        )
        logger.info(f'timesheet calc periods: {periods}')
        for period in periods:
            logger.debug(f'start period: {period}')
            self._calc(dt_start=period[0], dt_end=period[1])
            logger.debug(f'end period: {period}')
        logger.info(
            f'finish timesheet calc for employee with id={self.employee.id} tabel_code={self.employee.tabel_code}')
