import datetime
import logging
from decimal import Decimal

import pandas as pd
from django.db.models import Q, Subquery, OuterRef, Sum

from .fiscal import FiscalTimesheet, TimesheetItem
from ..models import WorkerDay, TimesheetItem as TimesheetItemModel

logger = logging.getLogger('calc_timesheets')

TIMESHEET_MAX_HOURS_THRESHOLD = Decimal('12.00')
TIMESHEET_MIN_HOURS_THRESHOLD = Decimal('4.00')


class BaseTimesheetDivider:
    def __init__(self, fiscal_timesheet: FiscalTimesheet):
        self.fiscal_timesheet = fiscal_timesheet

    def _is_holiday(self, item_data):
        if not item_data:
            return True

        if item_data.get('main_timesheet_type_id') is not None:
            timesheet_type = item_data.get('main_timesheet_type_id')
            timesheet_total_hours = item_data.get('main_timesheet_total_hours')
        else:
            timesheet_type = item_data.get('fact_timesheet_type_id')
            timesheet_total_hours = item_data.get('fact_timesheet_total_hours')

        wd_type_obj = self.fiscal_timesheet.wd_types_dict.get(timesheet_type)
        if wd_type_obj.is_dayoff or timesheet_total_hours == 0:
            return True

    def _get_outside_period_data(self, start_of_week, first_dt_weekday_num):
        if first_dt_weekday_num == 0:
            outside_period_data = {}
        else:
            dates_before_period = []
            for day in range(7):
                dt = start_of_week + datetime.timedelta(days=day)
                if day != first_dt_weekday_num:
                    dates_before_period.append(dt)

            outside_period_data = {i['dt']: i for i in TimesheetItemModel.objects.filter(
                employee=self.fiscal_timesheet.employee,
                dt__in=dates_before_period,
            ).values(
                'employee_id',
                'dt',
            ).annotate(
                fact_timesheet_type_id=Subquery(TimesheetItemModel.objects.filter(
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    timesheet_type=TimesheetItemModel.TIMESHEET_TYPE_FACT,
                ).order_by('-day_type__ordering').values('day_type_id')[:1]),
                fact_timesheet_total_hours=Sum('day_hours',
                                               filter=Q(timesheet_type=TimesheetItemModel.TIMESHEET_TYPE_FACT))
                                           + Sum('night_hours',
                                                 filter=Q(timesheet_type=TimesheetItemModel.TIMESHEET_TYPE_FACT)),
                main_timesheet_type_id=Subquery(TimesheetItemModel.objects.filter(
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    timesheet_type=TimesheetItemModel.TIMESHEET_TYPE_MAIN,
                ).order_by('-day_type__ordering').values('day_type_id')[:1]),
                main_timesheet_total_hours=Sum('day_hours',
                                               filter=Q(timesheet_type=TimesheetItemModel.TIMESHEET_TYPE_MAIN))
                                           + Sum('night_hours',
                                                 filter=Q(timesheet_type=TimesheetItemModel.TIMESHEET_TYPE_MAIN)),
            ).order_by(
                'dt',
            )}
        return outside_period_data

    def _make_holiday(self, dt):
        logger.info(f'make holiday {dt}')
        active_employment = self.fiscal_timesheet._get_active_employment(dt)
        main_timesheet_items = self.fiscal_timesheet.main_timesheet.pop(dt)
        self.fiscal_timesheet.main_timesheet.add(dt, TimesheetItem(
            shop=active_employment.shop,
            position=active_employment.position,
            day_type=self.fiscal_timesheet.wd_types_dict.get(WorkerDay.TYPE_HOLIDAY),
        ))
        self.fiscal_timesheet.additional_timesheet.add(dt, main_timesheet_items)

    def _check_weekly_continuous_holidays(self):
        logger.info(f'start weekly continuous holidays check')
        first_dt_weekday_num = self.fiscal_timesheet.dt_from.weekday()  # 0 - monday, 6 - sunday
        start_of_week = self.fiscal_timesheet.dt_from - datetime.timedelta(days=first_dt_weekday_num)
        outside_period_data = self._get_outside_period_data(start_of_week, first_dt_weekday_num)
        # если в последней неделе месяца 2 или более дней выходит за рамки месяца, то останавливаемся
        dt_stop = self.fiscal_timesheet.dt_to - datetime.timedelta(days=5)
        logger.debug(f'stop dt: {dt_stop}')
        while start_of_week <= dt_stop:
            continuous_holidays_count = 0
            first_holiday_found_dt = None
            week_dates = pd.date_range(start_of_week, start_of_week + datetime.timedelta(days=6)).date
            prev_day_is_holiday = False
            logger.debug(f'start week with start_of_week: {start_of_week}')
            for dt in week_dates:
                if self.fiscal_timesheet.dt_from <= dt <= self.fiscal_timesheet.dt_to:
                    current_day_is_holiday = self.fiscal_timesheet.main_timesheet.is_holiday(dt=dt)
                else:
                    current_day_is_holiday = self._is_holiday(outside_period_data.get(dt))

                if prev_day_is_holiday and current_day_is_holiday:
                    continuous_holidays_count = 2
                    logger.debug(f'prev_day_is_holiday and current_day_is_holiday, break')
                    break

                if current_day_is_holiday and not first_holiday_found_dt:
                    continuous_holidays_count = 1
                    first_holiday_found_dt = dt

                prev_day_is_holiday = current_day_is_holiday
            logger.debug(f'end week continuous_holidays_count: {continuous_holidays_count}, '
                         f'first_holiday_found_dt:{first_holiday_found_dt}')

            if continuous_holidays_count == 2:
                start_of_week += datetime.timedelta(days=7)
                logger.debug(f'continuous_holidays_count == 2, break')
                continue

            if continuous_holidays_count == 1:
                first_holiday_found_weekday = first_holiday_found_dt.weekday()
                logger.debug(
                    f'continuous_holidays_count == 1, first_holiday_found_weekday={first_holiday_found_weekday}')
                if first_holiday_found_weekday == 6:  # sunday
                    dt = first_holiday_found_dt - datetime.timedelta(days=1)
                else:
                    dt = first_holiday_found_dt + datetime.timedelta(days=1)
                logger.debug(
                    f'second found holiday {dt}')
                self._make_holiday(dt)
                start_of_week += datetime.timedelta(days=7)

            if continuous_holidays_count == 0:
                logger.debug(f'continuous_holidays_count == 0, make last 2 days of week as holidays')
                for dt in [week_dates[5], week_dates[6]]:
                    self._make_holiday(dt)

        logger.info(f'finish weekly continuous holidays check')

    def _check_not_more_than_threshold_hours(self):
        for dt in pd.date_range(self.fiscal_timesheet.dt_from, self.fiscal_timesheet.dt_to).date:
            main_timesheet_total_hours_sum = self.fiscal_timesheet.main_timesheet.get_total_hours_sum(dt)
            hours_overflow = main_timesheet_total_hours_sum - TIMESHEET_MAX_HOURS_THRESHOLD
            if hours_overflow > 0:
                subtracted_items = self.fiscal_timesheet.main_timesheet.subtract_hours(
                    dt=dt, hours_to_subtract=hours_overflow)
                if subtracted_items:
                    self.fiscal_timesheet.additional_timesheet.add(dt, subtracted_items)

    def _get_overtime(self, norm_hours):
        return self.fiscal_timesheet.main_timesheet.get_total_hours_sum() - norm_hours

    def _get_subtract_filters(self, dt):
        return {}

    def _check_overtimes(self):
        logger.info(
            f'start overtimes check '
            f'main t h: {self.fiscal_timesheet.main_timesheet.get_total_hours_sum()} '
            f'add h: {self.fiscal_timesheet.additional_timesheet.get_total_hours_sum()}')
        from src.timetable.worker_day.stat import (
            WorkersStatsGetter,
        )
        worker_stats = WorkersStatsGetter(
            dt_from=self.fiscal_timesheet.dt_from,
            dt_to=self.fiscal_timesheet.dt_to,
            network=self.fiscal_timesheet.employee.user.network,
            employee_id=self.fiscal_timesheet.employee.id,
        ).run()

        try:
            norm_hours = Decimal(worker_stats[self.fiscal_timesheet.employee.id]['plan']['approved']['sawh_hours']['curr_month'])
        except KeyError:
            logger.exception(
                f'cant get norm_hours, stop overtime checking employee_id: {self.fiscal_timesheet.employee.id}, worker_stats: {worker_stats}')
            return

        logger.info(f'norm_hours: {norm_hours}')
        overtime_plan = self._get_overtime(norm_hours)  # плановые переработки
        logger.info(f'overtime_plan at the beginning: {overtime_plan}')

        for dt in pd.date_range(self.fiscal_timesheet.dt_from, self.fiscal_timesheet.dt_to).date:
            subtract_filters = self._get_subtract_filters(dt=dt)
            if overtime_plan == 0.0:  # не будет ли проблем из-за того, что часы у нас не целые часы?
                logger.debug('overtime_plan == 0.0, break')
                break

            if self.fiscal_timesheet.main_timesheet.is_holiday(dt):
                continue

            if overtime_plan > 0:
                default_threshold_hours = TIMESHEET_MIN_HOURS_THRESHOLD
                main_timesheet_total_hours = self.fiscal_timesheet.main_timesheet.get_total_hours_sum(dt)
                hours_overflow = main_timesheet_total_hours - default_threshold_hours
                hours_transfer = min(hours_overflow, overtime_plan)

                subtracted_items = self.fiscal_timesheet.main_timesheet.subtract_hours(
                    dt=dt, hours_to_subtract=hours_transfer,
                    filters=subtract_filters,
                )
                self.fiscal_timesheet.additional_timesheet.add(dt=dt, timesheet_item=subtracted_items)
                if subtracted_items:
                    moved_hours = sum(i.total_hours for i in subtracted_items)
                    overtime_plan -= moved_hours
                continue
            else:
                if not self.fiscal_timesheet.additional_timesheet.get_total_hours_sum():
                    break

                additional_timesheet_hours = self.fiscal_timesheet.additional_timesheet.get_total_hours_sum(dt=dt)
                if not additional_timesheet_hours:
                    continue

                main_timesheet_day_hours = self.fiscal_timesheet.main_timesheet.get_day_hours_sum(dt=dt)
                main_timesheet_night_hours = self.fiscal_timesheet.main_timesheet.get_night_hours_sum(dt=dt)
                main_timesheet_total_hours = main_timesheet_day_hours + main_timesheet_night_hours
                if abs(overtime_plan) >= additional_timesheet_hours:
                    if main_timesheet_total_hours + additional_timesheet_hours <= TIMESHEET_MAX_HOURS_THRESHOLD:
                        hours_transfer = additional_timesheet_hours
                        subtracted_items = self.fiscal_timesheet.additional_timesheet.subtract_hours(
                            dt=dt, hours_to_subtract=hours_transfer,
                            filters=subtract_filters,
                        )
                        self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=subtracted_items)
                        overtime_plan += hours_transfer
                        continue
                    else:
                        threshold_hours = TIMESHEET_MAX_HOURS_THRESHOLD
                        hours_transfer = threshold_hours - main_timesheet_total_hours
                        subtracted_items = self.fiscal_timesheet.additional_timesheet.subtract_hours(
                            dt=dt, hours_to_subtract=hours_transfer,
                            filters=subtract_filters,
                        )
                        self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=subtracted_items)
                        overtime_plan += hours_transfer
                        continue
                else:
                    if main_timesheet_total_hours + abs(overtime_plan) <= TIMESHEET_MAX_HOURS_THRESHOLD:
                        hours_transfer = abs(overtime_plan)
                        subtracted_items = self.fiscal_timesheet.additional_timesheet.subtract_hours(
                            dt=dt, hours_to_subtract=hours_transfer,
                            filters=subtract_filters,
                        )
                        self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=subtracted_items)
                        overtime_plan += hours_transfer
                        continue
                    else:
                        threshold_hours = TIMESHEET_MAX_HOURS_THRESHOLD
                        hours_transfer = threshold_hours - main_timesheet_total_hours
                        subtracted_items = self.fiscal_timesheet.additional_timesheet.subtract_hours(
                            dt=dt, hours_to_subtract=hours_transfer,
                            filters=subtract_filters,
                        )
                        self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=subtracted_items)
                        overtime_plan += hours_transfer
                        continue

        logger.info(f'finish overtimes check, overtime_plan: {overtime_plan} '
                    f'main t h: {self.fiscal_timesheet.main_timesheet.get_total_hours_sum()} '
                    f'add h: {self.fiscal_timesheet.additional_timesheet.get_total_hours_sum()}')

    def _fill_main_timesheet(self):
        for dt in pd.date_range(self.fiscal_timesheet.dt_from, self.fiscal_timesheet.dt_to).date:
            fact_timesheet_items = filter(
                lambda i: i.day_type.is_dayoff or i.day_type.is_work_hours, self.fiscal_timesheet.fact_timesheet.get_items(dt))
            if fact_timesheet_items:
                for fact_timesheet_item in fact_timesheet_items:
                    self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=fact_timesheet_item.copy())
            else:
                active_employment = self.fiscal_timesheet._get_active_employment(dt)
                self.fiscal_timesheet.main_timesheet.add(TimesheetItem(
                    shop=active_employment.shop,
                    position=active_employment.position,
                    day_type=self.fiscal_timesheet.wd_types_dict.get(WorkerDay.TYPE_HOLIDAY),
                ))


class PobedaTimesheetDivider(BaseTimesheetDivider):
    def _move_other_shop_or_position_work_to_additional_timesheet(self):
        for dt in pd.date_range(self.fiscal_timesheet.dt_from, self.fiscal_timesheet.dt_to).date:
            active_employment = self.fiscal_timesheet._get_active_employment(dt)
            for main_timesheet_item in self.fiscal_timesheet.main_timesheet.get_items(dt=dt):
                if main_timesheet_item.position != active_employment.position \
                        or main_timesheet_item.shop != active_employment.shop:
                    self.fiscal_timesheet.main_timesheet.remove(dt, main_timesheet_item)
                    self.fiscal_timesheet.additional_timesheet.add(dt, main_timesheet_item)

    def _fill_empty_dates_as_holidays_in_main_timesheet(self):
        for dt in pd.date_range(self.fiscal_timesheet.dt_from, self.fiscal_timesheet.dt_to).date:
            active_employment = self.fiscal_timesheet._get_active_employment(dt)
            main_timesheet_items = self.fiscal_timesheet.main_timesheet.get_items(dt=dt)
            if not main_timesheet_items:
                self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=TimesheetItem(
                    shop=active_employment.shop,
                    position=active_employment.position,
                    day_type=self.fiscal_timesheet.wd_types_dict.get(WorkerDay.TYPE_HOLIDAY),
                ))

    def _get_subtract_filters(self, dt):
        active_employment = self.fiscal_timesheet._get_active_employment(dt)
        return {
            'position': active_employment.position,
            'shop': active_employment.shop,
        }

    def divide(self):
        logger.info(f'start fiscal sheet divide')
        self._fill_main_timesheet()
        self._move_other_shop_or_position_work_to_additional_timesheet()
        self._check_weekly_continuous_holidays()
        self._check_not_more_than_threshold_hours()
        self._check_overtimes()
        self._fill_empty_dates_as_holidays_in_main_timesheet()
        logger.info(f'finish fiscal sheet divide')


class NahodkaTimesheetDivider(BaseTimesheetDivider):
    def divide(self):
        logger.info(f'start fiscal sheet divide')
        self._fill_main_timesheet()
        self._check_weekly_continuous_holidays()
        self._check_not_more_than_threshold_hours()
        self._check_overtimes()
        logger.info(f'finish fiscal sheet divide')


FISCAL_SHEET_DIVIDERS_MAPPING = {
    'nahodka': NahodkaTimesheetDivider,
    'pobeda': PobedaTimesheetDivider,
}
