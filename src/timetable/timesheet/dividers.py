import datetime
import logging

import pandas as pd

from ..models import WorkerDay, Timesheet

logger = logging.getLogger('calc_timesheets')


class BaseTimesheetDivider:
    def __init__(self, employee, fiscal_sheet_dict, dt_start, dt_end):
        self.employee = employee
        self.fiscal_sheet_dict = fiscal_sheet_dict
        self.fiscal_sheet_list = sorted(list(fiscal_sheet_dict.values()), key=lambda i: i['dt'])
        self.dt_start = dt_start
        self.dt_end = dt_end

    def _is_holiday(self, item_data):
        if not item_data:
            return True

        if item_data.get('main_timesheet_type') is not None:
            timesheet_type = item_data.get('main_timesheet_type')
            timesheet_total_hours = item_data.get('main_timesheet_total_hours')
        else:
            timesheet_type = item_data.get('fact_timesheet_type')
            timesheet_total_hours = item_data.get('fact_timesheet_total_hours')

        if timesheet_type not in WorkerDay.TYPES_WITH_TM_RANGE or timesheet_total_hours == 0:
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

            outside_period_data = {i['dt']: i for i in Timesheet.objects.filter(
                employee=self.employee,
                dt__in=dates_before_period,
            ).values(
                'employee_id',
                'dt',
                'fact_timesheet_type',
                'fact_timesheet_total_hours',
                'main_timesheet_type',
                'main_timesheet_total_hours',
            ).order_by(
                'dt',
            )}
        return outside_period_data

    def _make_holiday(self, dt):
        logger.info(f'make holiday {dt}')
        data = self.fiscal_sheet_dict.get(dt)
        if data:
            data['additional_timesheet_hours'] = data['main_timesheet_total_hours']
            data['main_timesheet_type'] = WorkerDay.TYPE_HOLIDAY
            data.pop('main_timesheet_total_hours', None)
            data.pop('main_timesheet_day_hours', None)
            data.pop('main_timesheet_night_hours', None)

    def _check_weekly_continuous_holidays(self):
        logger.info(f'start weekly continuous holidays check')
        first_dt_weekday_num = self.dt_start.weekday()  # 0 - monday, 6 - sunday
        start_of_week = self.dt_start - datetime.timedelta(days=first_dt_weekday_num)
        outside_period_data = self._get_outside_period_data(start_of_week, first_dt_weekday_num)
        # если в последней неделе месяца 2 или более дней выходит за рамки месяца, то останавливаемся
        dt_stop = self.dt_end - datetime.timedelta(days=5)
        logger.debug(f'stop dt: {dt_stop}')
        while start_of_week <= dt_stop:
            continuous_holidays_count = 0
            first_holiday_found_dt = None
            week_dates = pd.date_range(start_of_week, start_of_week + datetime.timedelta(days=6)).date
            prev_day_is_holiday = False
            logger.debug(f'start week with start_of_week: {start_of_week}')
            for dt in week_dates:
                dt_data = self.fiscal_sheet_dict.get(dt) or outside_period_data.get(dt)
                current_day_is_holiday = self._is_holiday(dt_data)

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

    def _fill_main_timesheet(self):
        for data in self.fiscal_sheet_list:
            data['main_timesheet_type'] = data.get('fact_timesheet_type', '')
            if data['main_timesheet_type'] in WorkerDay.TYPES_WITH_TM_RANGE:
                data['main_timesheet_total_hours'] = data.get('fact_timesheet_total_hours')
                data['main_timesheet_day_hours'] = data.get('fact_timesheet_day_hours')
                data['main_timesheet_night_hours'] = data.get('fact_timesheet_night_hours')

    def _check_not_more_than_12_hours(self):
        for data in self.fiscal_sheet_list:
            self._move_hours_from_main_to_additional(data, threshold_hours=12.0)

    def _get_main_timesheet_total_hours(self):
        return sum(i.get('main_timesheet_total_hours', 0.0) for i in self.fiscal_sheet_list)

    def _get_overtime(self, norm_hours):
        return self._get_main_timesheet_total_hours() - norm_hours

    def _move_hours_from_main_to_additional(self, data, threshold_hours):
        """
        Перенос часов из осн. в доп. табель если суммарное кол-во часов в осн. табеле превышает threshold_hours
        (в приоритете за счет ночных часов)
        """
        hours_overflow = None
        if data['main_timesheet_type'] in WorkerDay.TYPES_WITH_TM_RANGE:
            hours_overflow = data.get('main_timesheet_total_hours') - threshold_hours
            if hours_overflow > 0:
                logger.debug(f'dt: {data["dt"]} has overflow threshold_hours: {threshold_hours} hours_overflow: {hours_overflow}')
                if data['main_timesheet_night_hours']:
                    logger.debug(f'has night hours: {data["main_timesheet_night_hours"]}')
                    if hours_overflow < data['main_timesheet_night_hours']:
                        logger.debug("hours_overflow < data['main_timesheet_night_hours']")
                        logger.debug(f"prev hours: main n: {data['main_timesheet_night_hours']} main t "
                            f"{data['main_timesheet_total_hours']} add h {data.get('additional_timesheet_hours', 0.0)}")
                        data['main_timesheet_night_hours'] = data['main_timesheet_night_hours'] - hours_overflow
                        data['main_timesheet_total_hours'] = threshold_hours
                        data['additional_timesheet_hours'] = data.get('additional_timesheet_hours',
                                                                      0.0) + hours_overflow

                        logger.debug(f"new hours: main n: {data['main_timesheet_night_hours']} main t "
                            f"{data['main_timesheet_total_hours']} add h {data.get('additional_timesheet_hours', 0.0)}")
                        return hours_overflow
                    else:
                        logger.debug("hours_overflow >= data['main_timesheet_night_hours']")
                        logger.debug(f"prev hours: main n: {data['main_timesheet_night_hours']} main d"
                                     f" {data['main_timesheet_day_hours']} main t {data['main_timesheet_total_hours']}"
                                     f" add h {data.get('additional_timesheet_hours', 0.0)}")
                        data['main_timesheet_night_hours'] = 0.0
                        data['main_timesheet_day_hours'] = threshold_hours
                        data['main_timesheet_total_hours'] = threshold_hours
                        data['additional_timesheet_hours'] = data.get('additional_timesheet_hours',
                                                                      0.0) + hours_overflow

                        logger.debug(f"new hours: main n: {data['main_timesheet_night_hours']} main d"
                                     f" {data['main_timesheet_day_hours']} main t {data['main_timesheet_total_hours']}"
                                     f" add h {data.get('additional_timesheet_hours', 0.0)}")
                        return hours_overflow
                else:
                    logger.debug('no night hours')
                    logger.debug(f"prev hours: main d {data['main_timesheet_day_hours']}"
                                 f" main t {data['main_timesheet_total_hours']}"
                                 f" add h {data.get('additional_timesheet_hours', 0.0)}")
                    data['main_timesheet_day_hours'] = data['main_timesheet_day_hours'] - hours_overflow
                    data['main_timesheet_total_hours'] = threshold_hours
                    data['additional_timesheet_hours'] = data.get('additional_timesheet_hours',
                                                                  0.0) + hours_overflow

                    logger.debug(f"new hours: main d {data['main_timesheet_day_hours']}"
                                 f" main t {data['main_timesheet_total_hours']}"
                                 f" add h {data.get('additional_timesheet_hours', 0.0)}")
                    return hours_overflow

        return hours_overflow

    def _get_additional_timesheet_hours(self):
        return sum(i.get('additional_timesheet_hours', 0.0) for i in self.fiscal_sheet_list)

    def _check_overtimes(self):
        logger.info(
            f'start overtimes check '
            f'main t h: {self._get_main_timesheet_total_hours()} '
            f'add h: {self._get_additional_timesheet_hours()}')
        from src.timetable.worker_day.stat import (
            WorkersStatsGetter,
        )
        worker_stats = WorkersStatsGetter(
            dt_from=self.dt_start,
            dt_to=self.dt_end,
            network=self.employee.user.network,
            employee_id=self.employee.id,
        ).run()

        # TODO: брать norm_hours (произв. календ.) для каких-то категорий сотрудников?
        try:
            norm_hours = worker_stats[self.employee.id]['plan']['approved']['sawh_hours']['curr_month']
        except KeyError:
            logger.exception(
                f'cant get norm_hours, stop overtime checking employee_id: {self.employee.id}, worker_stats: {worker_stats}')
            return
        logger.info(f'norm_hours: {norm_hours}')
        overtime_plan = self._get_overtime(norm_hours)  # плановые переработки
        logger.info(f'overtime_plan at the beginning: {overtime_plan}')

        for data in self.fiscal_sheet_list:
            if overtime_plan == 0.0:  # не будет ли проблем из-за того, что часы у нас не целые часы?
                logger.debug('overtime_plan == 0.0, break')
                break

            if data.get('main_timesheet_type') not in WorkerDay.TYPES_WITH_TM_RANGE or data.get(
                    'main_timesheet_total_hours') == 0.0:
                continue

            if overtime_plan > 0:
                default_threshold_hours = 4.0
                hours_overflow = data.get('main_timesheet_total_hours') - default_threshold_hours
                threshold_hours = default_threshold_hours if hours_overflow <= overtime_plan else data.get(
                    'main_timesheet_total_hours') - overtime_plan
                moved_hours = self._move_hours_from_main_to_additional(data, threshold_hours=threshold_hours)
                if moved_hours:
                    overtime_plan -= moved_hours
                continue
            else:
                if not self._get_additional_timesheet_hours():
                    break

                if not data.get('additional_timesheet_hours'):
                    continue

                if abs(overtime_plan) >= data.get('additional_timesheet_hours'):
                    if data.get('main_timesheet_total_hours') + data.get('additional_timesheet_hours', 0.0) <= 12.0:
                        hours_transfer = data.get('additional_timesheet_hours')
                        data['main_timesheet_total_hours'] += hours_transfer
                        data['main_timesheet_day_hours'] += hours_transfer
                        data.pop('additional_timesheet_hours', None)
                        overtime_plan += hours_transfer
                        continue
                    else:
                        threshold_hours = 12.0
                        hours_transfer = threshold_hours - data.get('main_timesheet_total_hours')
                        data['main_timesheet_total_hours'] += hours_transfer
                        data['main_timesheet_day_hours'] += hours_transfer
                        data['additional_timesheet_hours'] -= hours_transfer
                        overtime_plan += hours_transfer
                        continue
                else:
                    if data.get('main_timesheet_total_hours') + abs(overtime_plan) <= 12.0:
                        hours_transfer = abs(overtime_plan)
                        data['main_timesheet_total_hours'] += hours_transfer
                        data['main_timesheet_day_hours'] += hours_transfer
                        data['additional_timesheet_hours'] -= hours_transfer
                        overtime_plan += hours_transfer
                        continue
                    else:
                        threshold_hours = 12.0
                        hours_transfer = threshold_hours - data.get('main_timesheet_total_hours')
                        data['main_timesheet_total_hours'] += hours_transfer
                        data['main_timesheet_day_hours'] += hours_transfer
                        data['additional_timesheet_hours'] -= hours_transfer
                        overtime_plan += hours_transfer
                        continue

        logger.info(f'finish overtimes check, overtime_plan: {overtime_plan} '
                    f'main t h: {self._get_main_timesheet_total_hours()} '
                    f'add h: {self._get_additional_timesheet_hours()}')

    def divide(self):
        logger.info(f'start fiscal sheet divide')
        timesheet_data = self.fiscal_sheet_dict
        self._fill_main_timesheet()
        self._check_weekly_continuous_holidays()
        self._check_not_more_than_12_hours()
        self._check_overtimes()
        logger.info(f'finish fiscal sheet divide')
        return timesheet_data


class NahodkaTimesheetDivider(BaseTimesheetDivider):
    pass


FISCAL_SHEET_DIVIDERS_MAPPING = {
    'nahodka': NahodkaTimesheetDivider
}
