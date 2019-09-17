import functools
from datetime import timedelta
import pandas

from django.db.models import F, Sum, Min, Max, Q, Case, When, Value, IntegerField, Count
from django.db.models.functions import Extract

from src.db.models import (
    AttendanceRecords,
    User
)


def get_queryset(request, form):
    worker_ids = form['worker_ids']
    from_dt = form['from_dt']
    to_dt = form['to_dt']

    user_records = AttendanceRecords.objects.filter(
        dttm__date__gte=from_dt,
        dttm__date__lte=to_dt,
        shop_id=form['shop_id'],
    )

    if len(worker_ids):
        user_records = user_records.filter(
            Q(user_id__in=worker_ids) |
            Q(user_id__isnull=True) |
            Q(user__attachment_group=User.GROUP_OUTSOURCE)
        )
    if form['from_tm']:
        user_records = user_records.filter(dttm__time__gte=form['from_tm'])
    if form['to_tm']:
        user_records = user_records.filter(dttm__time__lte=form['to_tm'])
    if form['type']:
        user_records = user_records.filter(type=form['type'])

    select_not_verified = False
    select_not_detected = False
    select_workers = False
    select_outstaff = False

    if form['show_not_verified']:
        select_not_verified = Q(verified=False)

    if form['show_not_detected']:
        select_not_detected = Q(user_id__isnull=True)

    if form['show_workers']:
        select_workers = Q(user__attachment_group=User.GROUP_STAFF)

    if form['show_outstaff']:
        select_outstaff = Q(user__attachment_group=User.GROUP_OUTSOURCE)

    extra_filters = list(filter(lambda x: x, [select_not_verified, select_not_detected, select_workers, select_outstaff]))
    if len(extra_filters):
        extra_filters = functools.reduce(lambda x, y: x | y, extra_filters)
        user_records = user_records.filter(extra_filters)

    return user_records



def tick_stat_count(ticks):
    stat = {
        'hours_count': timedelta(hours=0),
        'ticks_coming_count': 0,
        'ticks_leaving_count': 0,
    }

    user_dt_type = {}
    for tick in ticks:
        dt = tick.dttm.date()
        if tick.user_id not in user_dt_type:
            user_dt_type[tick.user_id] = {}
        if dt not in user_dt_type[tick.user_id]:
            user_dt_type[tick.user_id][dt] = {
                AttendanceRecords.TYPE_COMING: [],
                AttendanceRecords.TYPE_LEAVING: []
            }
        if tick.type not in user_dt_type[tick.user_id][dt]:
            continue
        user_dt_type[tick.user_id][dt][tick.type].append(tick.dttm)

    for dt_type in user_dt_type.values():
        for type_dttm in dt_type.values():
            dttm_come = None
            dttm_leave = None
            if type_dttm[AttendanceRecords.TYPE_COMING]:
                stat['ticks_coming_count'] += 1
                dttm_come = min(type_dttm[AttendanceRecords.TYPE_COMING])

            if type_dttm[AttendanceRecords.TYPE_LEAVING]:
                stat['ticks_leaving_count'] += 1
                dttm_leave = max(type_dttm[AttendanceRecords.TYPE_LEAVING])

            if dttm_come and dttm_leave and dttm_come < dttm_leave:
                stat['hours_count'] += dttm_leave - dttm_come
    stat['hours_count'] = stat['hours_count'].total_seconds() / 3600
    return stat


# можно было бы всю статистику считать этой функцией, если бы не было отметок, для людей без расписания
# а так нужна еще tick_stat_count - статистика только по отметкам
def wd_stat_count(worker_days):
    return worker_days.values('worker_id', 'dt', 'dttm_work_start','dttm_work_end').annotate(
        coming=Min('worker__attendancerecords__dttm',
                     filter=Q(worker__attendancerecords__dttm__date=F('dt'),
                              worker__attendancerecords__type='C')),

        # leaving=Max('worker__attendancerecords__dttm',
        #               filter=Q(worker__attendancerecords__dttm__date=F('dt'),
        #                        worker__attendancerecords__type='L')),
        # hours_fact=F('leaving') - F('coming'),
        hours_plan=F('dttm_work_end') - F('dttm_work_start'),
        is_late=Case(
            When(coming__gt=F('dttm_work_start')-timedelta(minutes=15),
                 then=1),
            default=Value(0), output_field=IntegerField())
    ).aggregate(
         # hours_fact_count=Extract(Sum('hours_fact'), 'epoch') / 3600,
         hours_count_plan=Extract(Sum('hours_plan'),'epoch') / 3600,
         lateness_count=Sum('is_late'),
         # ticks_coming_count=Count('coming'),
         # ticks_leaving_count=Count('leaving')
    )

