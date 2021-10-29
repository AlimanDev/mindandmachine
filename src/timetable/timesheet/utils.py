from django.db.models import Q, F
from django.db.models import Sum

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

    worker_stats = WorkersStatsGetter(
        dt_from=dt_from,
        dt_to=dt_to,
        employee_id__in=timesheet_stats.keys(),
        network=user.network,
    ).run()
    for employee_id, data in timesheet_stats.items():
        data['norm_hours'] = worker_stats.get(
            employee_id, {}).get('plan', {}).get('approved', {}).get('norm_hours', {}).get('curr_month', None)
        data['sawh_hours'] = worker_stats.get(
            employee_id, {}).get('plan', {}).get('approved', {}).get('sawh_hours', {}).get('curr_month', None)

    return timesheet_stats
