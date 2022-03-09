import datetime
import logging
from decimal import Decimal

import pandas as pd
from django.conf import settings
from django.db.models import Q, Subquery, OuterRef, Sum
from django.utils import timezone
from django.utils.functional import cached_property
from src.base.shift_schedule.utils import get_shift_schedule

from .fiscal import FiscalTimesheet, TimesheetItem
from ..models import WorkerDay, TimesheetItem as TimesheetItemModel

logger = logging.getLogger('calc_timesheets')


class BaseTimesheetDivider:
    def __init__(self, fiscal_timesheet: FiscalTimesheet):
        self.fiscal_timesheet = fiscal_timesheet
        self.dt_now = timezone.now().date()

    def _is_holiday(self, item_data, consider_dayoff_work_hours=True):
        if not item_data:
            return True

        if item_data.get('main_timesheet_type_id') is not None:
            timesheet_type = item_data.get('main_timesheet_type_id')
            timesheet_total_hours = item_data.get('main_timesheet_total_hours')
        else:
            timesheet_type = item_data.get('fact_timesheet_type_id')
            timesheet_total_hours = item_data.get('fact_timesheet_total_hours')

        wd_type_obj = self.fiscal_timesheet.wd_types_dict.get(timesheet_type)
        if (wd_type_obj.is_dayoff and not wd_type_obj.is_work_hours) or (
                consider_dayoff_work_hours and wd_type_obj.is_dayoff and wd_type_obj.is_work_hours) or timesheet_total_hours == 0:
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
        if not self.fiscal_timesheet.dt_from <= dt <= self.fiscal_timesheet.dt_to:
            logger.info(f'can\'t make holiday {dt} for oustside period')  # TODO: за прошлый период надо проставлять выходной?
            return

        logger.info(f'make holiday {dt}')
        active_employment = self.fiscal_timesheet._get_active_employment(dt)
        if active_employment:
            main_timesheet_items = self.fiscal_timesheet.main_timesheet.pop(dt)
            self.fiscal_timesheet.main_timesheet.add(dt, TimesheetItem(
                dt=dt,
                shop=active_employment.shop,
                position=active_employment.position,
                work_type_name=self.fiscal_timesheet.work_type_names_dict.get(active_employment.main_work_type_name_id),
                day_type=self.fiscal_timesheet.wd_types_dict.get(WorkerDay.TYPE_HOLIDAY),
            ))
            self.fiscal_timesheet.additional_timesheet.add(dt, main_timesheet_items)

    def _need_to_skip_week(self, week_dates):
        prev_week_last_dt = week_dates[0] - datetime.timedelta(days=1)
        curr_week_first_dt = week_dates[0]
        curr_week_last_dt = week_dates[-1]
        if self.fiscal_timesheet.main_timesheet.is_holiday(dt=prev_week_last_dt, consider_dayoff_work_hours=False) and \
                self.fiscal_timesheet.main_timesheet.is_holiday(dt=curr_week_first_dt, consider_dayoff_work_hours=False) and \
                self.fiscal_timesheet.main_timesheet.is_holiday(dt=curr_week_last_dt, consider_dayoff_work_hours=False):
            return True

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
            holidays_found_dates = []
            week_dates = pd.date_range(start_of_week, start_of_week + datetime.timedelta(days=6)).date
            prev_day_is_holiday = False
            logger.debug(f'start week with start_of_week: {start_of_week}')

            if self._need_to_skip_week(week_dates):
                logger.debug(f'skip week: {start_of_week}-{start_of_week + datetime.timedelta(days=7)}')
                start_of_week += datetime.timedelta(days=7)
                continue

            for dt in week_dates:
                if self.fiscal_timesheet.dt_from <= dt <= self.fiscal_timesheet.dt_to:
                    current_day_is_holiday = self.fiscal_timesheet.main_timesheet.is_holiday(
                        dt=dt, consider_dayoff_work_hours=False)
                else:
                    current_day_is_holiday = self._is_holiday(
                        outside_period_data.get(dt), consider_dayoff_work_hours=False)

                if prev_day_is_holiday and current_day_is_holiday:
                    continuous_holidays_count = 2
                    logger.debug(f'prev_day_is_holiday and current_day_is_holiday, break')
                    break

                if current_day_is_holiday:
                    continuous_holidays_count = 1
                    holidays_found_dates.append(dt)

                prev_day_is_holiday = current_day_is_holiday
            logger.debug(f'end week continuous_holidays_count: {continuous_holidays_count}, '
                         f'holidays_found:{holidays_found_dates}')

            if continuous_holidays_count == 2:
                start_of_week += datetime.timedelta(days=7)
                logger.debug(f'continuous_holidays_count == 2, break')
                continue

            if continuous_holidays_count == 1:
                def _get_min_work_hours_and_dt(dt, prev_dt, min_wh):
                    work_hours = self.fiscal_timesheet.main_timesheet.get_total_hours_sum(dt=dt)
                    return (dt, work_hours) if work_hours < min_wh else (prev_dt, min_wh)

                min_work_hours = 24.0
                holiday_dt = None
                for dt in holidays_found_dates:
                    if dt.weekday() != 0:
                        holiday_dt, min_work_hours = _get_min_work_hours_and_dt(
                            dt - datetime.timedelta(1),
                            holiday_dt,
                            min_work_hours,
                        )
                    if dt.weekday() != 6:
                        holiday_dt, min_work_hours = _get_min_work_hours_and_dt(
                            dt + datetime.timedelta(1),
                            holiday_dt,
                            min_work_hours,
                        )
                
                logger.debug(
                    f'continuous_holidays_count == 1, second found holiday {holiday_dt}')
                self._make_holiday(holiday_dt)
                start_of_week += datetime.timedelta(days=7)

            if continuous_holidays_count == 0:
                logger.debug(f'continuous_holidays_count == 0, make last 2 days of week as holidays')
                for dt in [week_dates[5], week_dates[6]]:
                    self._make_holiday(dt)
                start_of_week += datetime.timedelta(days=7)

        logger.info(f'finish weekly continuous holidays check')

    def _check_not_more_than_threshold_hours(self):
        for dt in pd.date_range(self.fiscal_timesheet.dt_from, self.fiscal_timesheet.dt_to).date:
            main_timesheet_total_hours_sum = self.fiscal_timesheet.main_timesheet.get_total_hours_sum(dt)
            hours_overflow = main_timesheet_total_hours_sum - self.fiscal_timesheet.employee.user.network.timesheet_max_hours_threshold
            if hours_overflow > 0:
                subtracted_items = self.fiscal_timesheet.main_timesheet.subtract_hours(
                    dt=dt, hours_to_subtract=hours_overflow)
                if subtracted_items:
                    self.fiscal_timesheet.additional_timesheet.add(dt, subtracted_items)

    def _get_overtime(self, norm_hours):
        return self.fiscal_timesheet.main_timesheet.get_total_hours_sum() - norm_hours

    def _get_subtract_filters(self, active_employment, dt):
        return {}

    def _get_sawh_hours_key(self):
        return self.fiscal_timesheet.employee.user.network.timesheet_divider_sawh_hours_key

    def _get_min_hours_threshold(self, dt):
        active_employment = self.fiscal_timesheet._get_active_employment(dt)
        return self.fiscal_timesheet.employee.user.network.get_timesheet_min_hours_threshold(active_employment.norm_work_hours)

    def _check_overtimes(self):
        logger.info(
            f'start overtimes check '
            f'main t h: {self.fiscal_timesheet.main_timesheet.get_total_hours_sum()} '
            f'add h: {self.fiscal_timesheet.additional_timesheet.get_total_hours_sum()}')
        from src.timetable.worker_day.stat import (
            WorkersStatsGetter,
        )
        # получаем сеть из осн. тр-ва на начало периода, для того, чтобы корректно
        dt_from_active_employment = self.fiscal_timesheet._get_active_employment(dt=self.fiscal_timesheet.dt_from)
        network = dt_from_active_employment.shop.network if \
            dt_from_active_employment else self.fiscal_timesheet.employee.user.network

        worker_stats = WorkersStatsGetter(
            dt_from=self.fiscal_timesheet.dt_from,
            dt_to=self.fiscal_timesheet.dt_to,
            network=network,
            employee_id=self.fiscal_timesheet.employee.id,
        ).run()

        try:
            norm_hours = Decimal(worker_stats[self.fiscal_timesheet.employee.id]['plan']['approved']['sawh_hours'][self._get_sawh_hours_key()])
        except KeyError:
            logger.exception(
                f'cant get norm_hours, stop overtime checking employee_id: {self.fiscal_timesheet.employee.id}, worker_stats: {worker_stats}')
            return

        logger.info(f'norm_hours: {norm_hours}')
        overtime_plan = self._get_overtime(norm_hours)  # плановые переработки
        logger.info(f'overtime_plan at the beginning: {overtime_plan}')

        for dt in pd.date_range(self.fiscal_timesheet.dt_from, self.fiscal_timesheet.dt_to).date:
            active_employment = self.fiscal_timesheet._get_active_employment(dt)
            if not active_employment:
                continue

            subtract_filters = self._get_subtract_filters(active_employment=active_employment, dt=dt)
            if overtime_plan == 0.0:  # не будет ли проблем из-за того, что часы у нас не целые часы?
                logger.debug('overtime_plan == 0.0, break')
                break

            if self.fiscal_timesheet.main_timesheet.is_holiday(dt):
                continue

            if overtime_plan > 0:
                default_threshold_hours = self._get_min_hours_threshold(dt=dt)
                main_timesheet_total_hours = self.fiscal_timesheet.main_timesheet.get_total_hours_sum(dt)
                hours_overflow = main_timesheet_total_hours - default_threshold_hours
                hours_transfer = min(hours_overflow, overtime_plan)
                if hours_transfer > 0:
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

                additional_timesheet_hours = self.fiscal_timesheet.additional_timesheet.get_total_hours_sum(
                    dt=dt, filter_func=lambda i: not i.freezed)
                if not additional_timesheet_hours:
                    continue

                main_timesheet_day_hours = self.fiscal_timesheet.main_timesheet.get_day_hours_sum(dt=dt)
                main_timesheet_night_hours = self.fiscal_timesheet.main_timesheet.get_night_hours_sum(dt=dt)
                main_timesheet_total_hours = main_timesheet_day_hours + main_timesheet_night_hours
                if abs(overtime_plan) >= additional_timesheet_hours:
                    if main_timesheet_total_hours + additional_timesheet_hours <= self.fiscal_timesheet.employee.user.network.timesheet_max_hours_threshold:
                        hours_transfer = additional_timesheet_hours
                        subtracted_items = self.fiscal_timesheet.additional_timesheet.subtract_hours(
                            dt=dt, hours_to_subtract=hours_transfer,
                            filters=subtract_filters,
                        )
                        self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=subtracted_items)
                        overtime_plan += hours_transfer
                        continue
                    else:
                        threshold_hours = self.fiscal_timesheet.employee.user.network.timesheet_max_hours_threshold
                        hours_transfer = threshold_hours - main_timesheet_total_hours
                        subtracted_items = self.fiscal_timesheet.additional_timesheet.subtract_hours(
                            dt=dt, hours_to_subtract=hours_transfer,
                            filters=subtract_filters,
                        )
                        self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=subtracted_items)
                        overtime_plan += hours_transfer
                        continue
                else:
                    if main_timesheet_total_hours + abs(overtime_plan) <= self.fiscal_timesheet.employee.user.network.timesheet_max_hours_threshold:
                        hours_transfer = abs(overtime_plan)
                        subtracted_items = self.fiscal_timesheet.additional_timesheet.subtract_hours(
                            dt=dt, hours_to_subtract=hours_transfer,
                            filters=subtract_filters,
                        )
                        self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=subtracted_items)
                        overtime_plan += hours_transfer
                        continue
                    else:
                        threshold_hours = self.fiscal_timesheet.employee.user.network.timesheet_max_hours_threshold
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

    def _init_main_and_additional_timesheets(self):
        for dt in pd.date_range(self.fiscal_timesheet.dt_from, self.fiscal_timesheet.dt_to).date:
            day_in_past = dt < self.dt_now
            if self.fiscal_timesheet.employee.user.network.settings_values_prop.get(
                    'timesheet_only_day_in_past', False) and not day_in_past:
                continue
            fact_timesheet_items = list(filter(
                lambda i: i.day_type.is_dayoff or i.day_type.is_work_hours, self.fiscal_timesheet.fact_timesheet.get_items(dt)))
            if fact_timesheet_items:
                dayoff_items = list(filter(lambda i: i.day_type.is_dayoff, fact_timesheet_items))
                if dayoff_items:
                    dayoff_item = dayoff_items[0]
                    self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=dayoff_item.copy())

                    workday_items = list(filter(lambda i: not i.day_type.is_dayoff, fact_timesheet_items))
                    if workday_items:
                        for workday_item in workday_items:
                            self.fiscal_timesheet.additional_timesheet.add(
                                dt=dt,
                                timesheet_item=workday_item.copy(overrides={'freezed': True}),
                            )
                else:
                    for fact_timesheet_item in fact_timesheet_items:
                        self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=fact_timesheet_item.copy())
            else:
                active_employment = self.fiscal_timesheet._get_active_employment(dt)
                if active_employment:
                    self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=TimesheetItem(
                        dt=dt,
                        shop=active_employment.shop,
                        position=active_employment.position,
                        work_type_name=self.fiscal_timesheet.work_type_names_dict.get(active_employment.main_work_type_name_id),
                        day_type=self.fiscal_timesheet.wd_types_dict.get(WorkerDay.TYPE_HOLIDAY),
                    ))


class PobedaTimesheetDivider(BaseTimesheetDivider):
    def _move_other_shop_or_position_work_to_additional_timesheet(self):
        for dt in pd.date_range(self.fiscal_timesheet.dt_from, self.fiscal_timesheet.dt_to).date:
            active_employment = self.fiscal_timesheet._get_active_employment(dt)
            if active_employment:
                for main_timesheet_item in self.fiscal_timesheet.main_timesheet.get_items(dt=dt):
                    work_type_name_differs = \
                        main_timesheet_item.work_type_name and \
                        active_employment.main_work_type_name_id and \
                        main_timesheet_item.work_type_name.id != active_employment.main_work_type_name_id
                    position_differs = main_timesheet_item.position != active_employment.position
                    shop_differs = main_timesheet_item.shop != active_employment.shop
                    move_cond = (self.fiscal_timesheet.employee.user.network.settings_values_prop.get(
                        'move_to_add_timesheet_if_work_type_name_differs') and work_type_name_differs) \
                                or position_differs \
                                or shop_differs
                    if move_cond:
                        self.fiscal_timesheet.main_timesheet.remove(dt, main_timesheet_item)
                        self.fiscal_timesheet.additional_timesheet.add(
                            dt, main_timesheet_item.copy(overrides={'freezed': True}))

    def _fill_empty_dates_as_holidays_in_main_timesheet(self):
        for dt in pd.date_range(self.fiscal_timesheet.dt_from, self.fiscal_timesheet.dt_to).date:
            day_in_past = dt < self.dt_now
            if self.fiscal_timesheet.employee.user.network.settings_values_prop.get(
                    'timesheet_only_day_in_past', False) and not day_in_past:
                continue
            active_employment = self.fiscal_timesheet._get_active_employment(dt)
            if active_employment:
                main_timesheet_items = self.fiscal_timesheet.main_timesheet.get_items(dt=dt)
                if not main_timesheet_items:
                    self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=TimesheetItem(
                        dt=dt,
                        shop=active_employment.shop,
                        position=active_employment.position,
                        work_type_name=self.fiscal_timesheet.work_type_names_dict.get(active_employment.main_work_type_name_id),
                        day_type=self.fiscal_timesheet.wd_types_dict.get(WorkerDay.TYPE_HOLIDAY),
                    ))

    def _get_subtract_filters(self, active_employment, dt):
        return {
            'position': active_employment.position,
            'shop': active_employment.shop,
        }

    def _redistribute_vacations_from_additional_timesheet_to_main_timesheet(self):
        vacation_hours = Decimal('0.00')
        for additional_timesheet_item in self.fiscal_timesheet.additional_timesheet.get_items(
                filter_func=lambda i: i.day_type.code == WorkerDay.TYPE_VACATION):
            self.fiscal_timesheet.additional_timesheet.remove(
                additional_timesheet_item.dt, additional_timesheet_item)
            vacation_hours += additional_timesheet_item.total_hours

        if vacation_hours:
            items = self.fiscal_timesheet.main_timesheet.get_items(
                filter_func=lambda i: i.day_type.code == WorkerDay.TYPE_VACATION)
            if items:
                idx = 0
                while vacation_hours > 0:
                    idx = idx % len(items)
                    item = items[idx]
                    item.day_hours += min(1, vacation_hours)
                    vacation_hours -= min(1, vacation_hours)
                    idx += 1

    def _replace_sick_with_absence_type(self):
        for main_timesheet_item in self.fiscal_timesheet.main_timesheet.get_items(
                filter_func=lambda i: i.day_type.code == WorkerDay.TYPE_SICK):
            main_timesheet_item.day_type = self.fiscal_timesheet.wd_types_dict.get(WorkerDay.TYPE_ABSENSE)
        for add_timesheet_item in self.fiscal_timesheet.additional_timesheet.get_items(
                filter_func=lambda i: i.day_type.code == WorkerDay.TYPE_SICK):
            add_timesheet_item.day_type = self.fiscal_timesheet.wd_types_dict.get(WorkerDay.TYPE_ABSENSE)

    def _remove_absence_from_additional_timesheet(self):
        for additional_timesheet_item in self.fiscal_timesheet.additional_timesheet.get_items(
                filter_func=lambda i: i.day_type.code == WorkerDay.TYPE_ABSENSE):
            self.fiscal_timesheet.additional_timesheet.remove(additional_timesheet_item.dt, additional_timesheet_item)

    def divide(self):
        logger.info(f'start pobeda fiscal sheet divide')
        self._init_main_and_additional_timesheets()
        self._move_other_shop_or_position_work_to_additional_timesheet()
        self._check_weekly_continuous_holidays()
        self._replace_sick_with_absence_type()
        self._remove_absence_from_additional_timesheet()
        self._check_not_more_than_threshold_hours()
        self._redistribute_vacations_from_additional_timesheet_to_main_timesheet()
        self._check_overtimes()
        self._fill_empty_dates_as_holidays_in_main_timesheet()
        logger.info(f'finish pobeda fiscal sheet divide')


class NahodkaTimesheetDivider(BaseTimesheetDivider):
    def divide(self):
        logger.info(f'start nahodka fiscal sheet divide')
        self._init_main_and_additional_timesheets()
        self._check_weekly_continuous_holidays()
        self._check_not_more_than_threshold_hours()
        self._check_overtimes()
        logger.info(f'finish nahodka fiscal sheet divide')


class ShiftScheduleDivider(BaseTimesheetDivider):
    @cached_property
    def shift_schedule_data(self):
        return get_shift_schedule(
            network_id=self.fiscal_timesheet.employee.user.network_id,
            employee_id=self.fiscal_timesheet.employee.id,
            dt__gte=self.fiscal_timesheet.dt_from,
            dt__lte=self.fiscal_timesheet.dt_to,
        ).get(str(self.fiscal_timesheet.employee.id), {})

    @cached_property
    def plan_approved_data(self):
        return {wd.dt: wd for wd in WorkerDay.objects.filter(  # считаем, что в плане 1 смена
            is_fact=False,
            is_approved=True,
            employee_id=self.fiscal_timesheet.employee.id,
            dt__gte=self.fiscal_timesheet.dt_from,
            dt__lte=self.fiscal_timesheet.dt_to,
        ).order_by('type__is_dayoff')}

    def _move_from_additional_to_main_if_main_less_than_norm(self):
        for dt in pd.date_range(self.fiscal_timesheet.dt_from, self.fiscal_timesheet.dt_to).date:
            additional_timesheet_total_hours = self.fiscal_timesheet.additional_timesheet.get_total_hours_sum()
            if additional_timesheet_total_hours <= 0:
                return
            shift_schedule_hours = self.shift_schedule_data.get(str(dt), {}).get('work_hours', Decimal('0.00'))
            main_timesheet_total_hours = self.fiscal_timesheet.main_timesheet.get_total_hours_sum(dt=dt)
            if shift_schedule_hours and main_timesheet_total_hours < shift_schedule_hours:
                plan_approved_wd = self.plan_approved_data.get(dt)
                min_hours_threshold = self._get_min_hours_threshold(dt=dt)
                if plan_approved_wd and \
                        (main_timesheet_total_hours + additional_timesheet_total_hours) > min_hours_threshold:

                    # если в плане рабочий день или нерабочий день не снижающий норму
                    if (not plan_approved_wd.type.is_dayoff and plan_approved_wd.type.is_work_hours) or (
                            plan_approved_wd.type.is_dayoff and not plan_approved_wd.type.is_reduce_norm):
                        shift_schedule_day_hours = self.shift_schedule_data.get(str(dt), {}).get('day_hours', Decimal('0.00'))
                        shift_schedule_night_hours = self.shift_schedule_data.get(str(dt), {}).get('night_hours', Decimal('0.00'))

                        # костылик на случай если дневные и ночные часы не будут приходить
                        if not shift_schedule_day_hours and not shift_schedule_night_hours:
                            shift_schedule_day_hours = shift_schedule_hours

                        if main_timesheet_total_hours < shift_schedule_hours:
                            main_timesheet_night_hours = self.fiscal_timesheet.main_timesheet.get_night_hours_sum(dt=dt)
                            if main_timesheet_night_hours < shift_schedule_night_hours:
                                total_hours_to_subtract = Decimal(
                                    shift_schedule_hours) - self.fiscal_timesheet.main_timesheet.get_total_hours_sum(dt=dt)
                                night_hours_to_subtract = min(Decimal(shift_schedule_night_hours) - main_timesheet_night_hours, total_hours_to_subtract)
                                items = self.fiscal_timesheet.additional_timesheet.subtract_hours(
                                    hours_to_subtract=night_hours_to_subtract, field='night_hours')
                                self.fiscal_timesheet.main_timesheet.add(dt, items, inplace=True)

                            main_timesheet_day_hours = self.fiscal_timesheet.main_timesheet.get_day_hours_sum(dt=dt)
                            if main_timesheet_day_hours < shift_schedule_day_hours:
                                total_hours_to_subtract = Decimal(
                                    shift_schedule_hours) - self.fiscal_timesheet.main_timesheet.get_total_hours_sum(dt=dt)
                                day_hours_to_subtract = min(Decimal(shift_schedule_day_hours) - main_timesheet_day_hours, total_hours_to_subtract)
                                items = self.fiscal_timesheet.additional_timesheet.subtract_hours(
                                    hours_to_subtract=day_hours_to_subtract, field='day_hours')
                                self.fiscal_timesheet.main_timesheet.add(dt, items, inplace=True)

                            total_hours_to_subtract = Decimal(
                                shift_schedule_hours) - self.fiscal_timesheet.main_timesheet.get_total_hours_sum(dt=dt)
                            if total_hours_to_subtract <= shift_schedule_hours:
                                items = self.fiscal_timesheet.additional_timesheet.subtract_hours(
                                    hours_to_subtract=total_hours_to_subtract)
                                for item in items:
                                    item.day_hours = item.day_hours + item.night_hours
                                    item.night_hours = Decimal('0.00')
                                self.fiscal_timesheet.main_timesheet.add(dt, items, inplace=True)

    def _divide_by_shift_schedule(self):
        for dt in pd.date_range(self.fiscal_timesheet.dt_from, self.fiscal_timesheet.dt_to).date:
            day_in_past = dt < self.dt_now
            if self.fiscal_timesheet.employee.user.network.settings_values_prop.get(
                    'timesheet_only_day_in_past', False) and not day_in_past:
                continue
            fact_timesheet_items = list(filter(
                lambda i: i.day_type.is_dayoff or i.day_type.is_work_hours, self.fiscal_timesheet.fact_timesheet.get_items(dt)))
            if fact_timesheet_items:
                dayoff_items = list(filter(lambda i: i.day_type.is_dayoff, fact_timesheet_items))
                if dayoff_items:
                    dayoff_item = dayoff_items[0]
                    shift_schedule_day_type = self.shift_schedule_data.get(
                        str(dt), {}).get('day_type', WorkerDay.TYPE_HOLIDAY)
                    shift_schedule_day_type_obj = self.fiscal_timesheet.wd_types_dict.get(
                        shift_schedule_day_type)
                    override_kwargs = None
                    if not dayoff_item.day_type.is_reduce_norm and shift_schedule_day_type_obj.is_dayoff and (
                            dayoff_item.day_type.code != shift_schedule_day_type_obj.code):
                        override_kwargs = {'day_type': shift_schedule_day_type_obj}
                    self.fiscal_timesheet.main_timesheet.add(
                        dt=dt, timesheet_item=dayoff_item.copy(overrides=override_kwargs))

                    workday_items = list(filter(lambda i: not i.day_type.is_dayoff, fact_timesheet_items))
                    if workday_items:
                        for workday_item in workday_items:
                            self.fiscal_timesheet.additional_timesheet.add(
                                dt=dt,
                                timesheet_item=workday_item.copy(overrides={'freezed': True}),
                            )
                else:
                    for fact_timesheet_item in fact_timesheet_items:
                        self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=fact_timesheet_item.copy())
                        main_ts_hours = self.fiscal_timesheet.main_timesheet.get_total_hours_sum(dt=dt)
                        shift_schedule_hours = self.shift_schedule_data.get(str(dt), {}).get('work_hours', Decimal('0.00'))
                        if main_ts_hours > shift_schedule_hours:
                            shift_schedule_day_type = self.shift_schedule_data.get(
                                str(dt), {}).get('day_type', WorkerDay.TYPE_HOLIDAY)
                            shift_schedule_day_type_obj = self.fiscal_timesheet.wd_types_dict.get(
                                shift_schedule_day_type)
                            if shift_schedule_day_type_obj.is_dayoff or not shift_schedule_hours:
                                items = self.fiscal_timesheet.main_timesheet.pop(dt=dt)
                                for item in items:
                                    self.fiscal_timesheet.additional_timesheet.add(dt=dt, timesheet_item=item)
                                active_employment = self.fiscal_timesheet._get_active_employment(dt)
                                if active_employment:
                                    self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=TimesheetItem(
                                        dt=dt,
                                        shop=active_employment.shop,
                                        position=active_employment.position,
                                        work_type_name=self.fiscal_timesheet.work_type_names_dict.get(active_employment.main_work_type_name_id),
                                        day_type=shift_schedule_day_type_obj,
                                    ))
                            else:
                                hours_to_subtract = main_ts_hours - shift_schedule_hours
                                items = self.fiscal_timesheet.main_timesheet.subtract_hours(dt=dt, hours_to_subtract=hours_to_subtract)
                                for item in items:
                                    self.fiscal_timesheet.additional_timesheet.add(dt=dt, timesheet_item=item)
            else:
                active_employment = self.fiscal_timesheet._get_active_employment(dt)
                if active_employment:
                    self.fiscal_timesheet.main_timesheet.add(dt=dt, timesheet_item=TimesheetItem(
                        dt=dt,
                        shop=active_employment.shop,
                        position=active_employment.position,
                        work_type_name=self.fiscal_timesheet.work_type_names_dict.get(active_employment.main_work_type_name_id),
                        day_type=self.fiscal_timesheet.wd_types_dict.get(WorkerDay.TYPE_HOLIDAY),
                    ))

    def divide(self):
        logger.info(f'start shift_schedule fiscal sheet divide')
        self._divide_by_shift_schedule()
        self._move_from_additional_to_main_if_main_less_than_norm()
        logger.info(f'finish shift_schedule fiscal sheet divide')


FISCAL_SHEET_DIVIDERS_MAPPING = {
    'nahodka': NahodkaTimesheetDivider,
    'pobeda': PobedaTimesheetDivider,
    'shift_schedule': ShiftScheduleDivider,
}
