from typing import Iterable
from datetime import date

from django.db.models import Q, F, Sum, Exists, OuterRef

from src.base.models import Employment, Network
from ..models import WorkerDayType, TimesheetItem
from ..worker_day.stat import WorkersStatsGetter


def get_timesheet_stats(filtered_qs, dt_from, dt_to, user):
    timesheet_stats_qs = filtered_qs.values(
        'employee_id',
    ).annotate(
        fact_total_all_hours_sum=Sum(F('day_hours') + F('night_hours'), filter=Q(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT)),
        fact_total_work_hours_sum=Sum(F('day_hours') + F('night_hours'), filter=Q(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT, day_type__is_work_hours=True)),
        fact_day_work_hours_sum=Sum('day_hours', filter=Q(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT, day_type__is_work_hours=True)),
        fact_night_work_hours_sum=Sum('night_hours', filter=Q(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT, day_type__is_work_hours=True)),
        main_total_hours_sum=Sum(F('day_hours') + F('night_hours'), filter=Q(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)),
        main_day_hours_sum=Sum('day_hours', filter=Q(timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)),
        main_night_hours_sum=Sum('night_hours', filter=Q(timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)),
        additional_hours_sum=Sum(F('day_hours') + F('night_hours'), filter=Q(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL)),
    )
    hours_by_types = list(WorkerDayType.objects.filter(
        is_active=True,
        show_stat_in_hours=True,
    ).values_list('code', flat=True))
    if hours_by_types:
        hours_by_types_annotates = {}
        for type_id in hours_by_types:
            hours_by_types_annotates[f'hours_by_type_{type_id}'] = Sum(
                F('day_hours') + F('night_hours'), filter=Q(
                    timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT, day_type_id=type_id))
        timesheet_stats_qs = timesheet_stats_qs.annotate(**hours_by_types_annotates)

    timesheet_stats = {}
    for ts_data in timesheet_stats_qs:
        k = ts_data.pop('employee_id')
        if hours_by_types:
            hours_by_type_dict = {}
            for type_id in hours_by_types:
                hours_by_type_dict[type_id] = ts_data.pop(f'hours_by_type_{type_id}')
            ts_data['hours_by_type'] = hours_by_type_dict
        timesheet_stats[k] = ts_data

    employee_id__in = timesheet_stats.keys()
    if employee_id__in:
        worker_stats = WorkersStatsGetter(
            dt_from=dt_from,
            dt_to=dt_to,
            employee_id__in=employee_id__in,
            network=user.network,
        ).run()
        for employee_id, data in timesheet_stats.items():
            data['norm_hours'] = worker_stats.get(
                employee_id, {}).get('plan', {}).get('approved', {}).get('norm_hours', {}).get('curr_month', None)
            data['sawh_hours'] = worker_stats.get(
                employee_id, {}).get('plan', {}).get('approved', {}).get('sawh_hours', {}).get('curr_month', None)
            data['sawh_hours_without_reduce'] = worker_stats.get(
                employee_id, {}).get('plan', {}).get('approved', {}).get('sawh_hours', {}).get('curr_month_without_reduce_norm', None)

    return timesheet_stats

def delete_hanging_timesheet_items(calc_periods: Iterable[tuple[date, date]]) -> tuple[int, dict]:
    '''Удаляет `TimesheetItem` у сотрудников без активного трудоустройства на этот день'''
    range_q = Q()
    for period in calc_periods:
        range_q |= Q(dt__range=(*period,))
    return TimesheetItem.objects.filter(
        range_q
        ).exclude(
            Exists(
                Employment.objects.get_active(
                    dt_from=OuterRef('dt'), dt_to=OuterRef('dt')
                ).filter(employee=OuterRef('employee'))
            )
        ).delete()


class BaseTimesheetLinesGroupByStrategy:
    def get_extra_values(self):
        pass

    def get_values(self):
        values = [
            'timesheet_type',
            'employee_id',
            'employee__tabel_code',
        ]
        extra_values = self.get_extra_values()
        if extra_values:
            values.extend(extra_values)
        return values


class TimesheetLinesGroupByEmployeeStrategy(BaseTimesheetLinesGroupByStrategy):
    pass


class TimesheetLinesGroupByEmployeePositionStrategy(BaseTimesheetLinesGroupByStrategy):
    def get_extra_values(self):
        return [
            'position_id',
            'position__code',
        ]


class TimesheetLinesGroupByEmployeePositionShopStrategy(BaseTimesheetLinesGroupByStrategy):
    def get_extra_values(self):
        return [
            'position_id',
            'position__code',
            'shop_id',
            'shop__code',
        ]


class TimesheetLinesDataGetter:
    group_by_strategies_mapping = {
        'default': TimesheetLinesGroupByEmployeePositionShopStrategy,
        Network.TIMESHEET_LINES_GROUP_BY_EMPLOYEE_POSITION_SHOP: TimesheetLinesGroupByEmployeePositionShopStrategy,
        Network.TIMESHEET_LINES_GROUP_BY_EMPLOYEE_POSITION: TimesheetLinesGroupByEmployeePositionStrategy,
        Network.TIMESHEET_LINES_GROUP_BY_EMPLOYEE: TimesheetLinesGroupByEmployeeStrategy,
    }

    def __init__(self, timesheet_qs, user=None):
        self.timesheet_qs = timesheet_qs
        self.user = user
        self.group_by_strategy_cls = self._get_group_by_strategy_cls()

    def _get_group_by_strategy_cls(self):
        if self.user and self.user.network_id:
            return self.group_by_strategies_mapping.get(self.user.network.api_timesheet_lines_group_by)

        return self.group_by_strategies_mapping.get('default')

    def _get_ts_values(self):
        return self.group_by_strategy_cls().get_values()

    def get(self):
        ts_values = self._get_ts_values()
        ts_lines = self.timesheet_qs.values(*ts_values).distinct()
        for ts_line in ts_lines:
            ts_line_days = []
            days_qs = self.timesheet_qs.filter(**ts_line).values(
                'dt',
                'day_type',
            ).annotate(
                day_hours_sum=Sum('day_hours'),
                night_hours_sum=Sum('night_hours'),
            ).values_list(
                'dt',
                'day_type',
                'day_hours_sum',
                'night_hours_sum',
            )
            for dt, day_type, day_hours_sum, night_hours_sum in days_qs:
                if day_hours_sum or night_hours_sum:
                    if day_hours_sum:
                        ts_line_days.append({
                            'dt': dt,
                            'day_type': day_type,
                            'hours_type': 'D',
                            'hours': day_hours_sum,
                        })
                    if night_hours_sum:
                        ts_line_days.append({
                            'dt': dt,
                            'day_type': day_type,
                            'hours_type': 'N',
                            'hours': night_hours_sum,
                        })
                else:
                    ts_line_days.append({
                        'dt': dt,
                        'day_type': day_type,
                    })
            ts_line['days'] = ts_line_days
        return ts_lines
