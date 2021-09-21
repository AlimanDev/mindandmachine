from django.db.models import Sum

from ..worker_day.stat import WorkersStatsGetter


def get_timesheet_stats(filtered_qs, user, dt_from, dt_to):
    timesheet_stats_qs = filtered_qs.values(
        'employee_id',
    ).annotate(
        fact_total_hours_sum=Sum('fact_timesheet_total_hours'),
        fact_day_hours_sum=Sum('fact_timesheet_day_hours'),
        fact_night_hours_sum=Sum('fact_timesheet_night_hours'),
        main_total_hours_sum=Sum('main_timesheet_total_hours'),
        main_day_hours_sum=Sum('main_timesheet_day_hours'),
        main_night_hours_sum=Sum('main_timesheet_night_hours'),
        additional_hours_sum=Sum('additional_timesheet_hours'),
    )
    timesheet_stats = {}
    for ts_data in timesheet_stats_qs:
        k = ts_data.pop('employee_id')
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
