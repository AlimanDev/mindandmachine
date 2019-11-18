from datetime import timedelta

from django.db.models import (
    Count, F, Sum, Min, Max, Q, Case, When, Value, IntegerField, DateTimeField, FloatField)
from django.db.models.functions import Extract, Coalesce, Cast

from src.db.models import (
    AttendanceRecords,
    WorkerDay
)


def wd_stat_count(worker_days):
    return worker_days.filter(
        type=WorkerDay.Type.TYPE_WORKDAY.value
    ).values('worker_id', 'dt', 'dttm_work_start','dttm_work_end').annotate(
        coming=Min('worker__attendancerecords__dttm', filter=Q(
            worker__attendancerecords__dttm__date=F('dt'),
            worker__attendancerecords__type=AttendanceRecords.TYPE_COMING
        )),

        leaving=Max('worker__attendancerecords__dttm',
                      filter=Q(worker__attendancerecords__dttm__date=F('dt'),
                               worker__attendancerecords__type='L')),
        hours_plan=Cast(Extract(F('dttm_work_end') - F('dttm_work_start'), 'epoch') / 3600, FloatField()),
        is_late=Case(
            When(coming__gt=F('dttm_work_start')-timedelta(minutes=15), then=1),
            default=Value(0), output_field=IntegerField()),
        hours_fact=Cast(
            Extract(Coalesce(
                Case(When(leaving__gt=F('dttm_work_end'), then=F('dttm_work_end')),
                        default=F('leaving'), output_field=DateTimeField())
                -
                Case(When(coming__lt=F('dttm_work_start'), then=F('dttm_work_start')),
                    default=F('coming'), output_field=DateTimeField()),
                timedelta(hours=0)), 'epoch') / 3600,
            IntegerField()),
    )


def wd_stat_count_total(worker_days):
    return wd_stat_count(worker_days).aggregate(
         hours_count_fact=Sum('hours_fact'),
         hours_count_plan=Sum('hours_plan'),
         lateness_count=Sum('is_late'),
         ticks_coming_count=Count('coming'),
         ticks_leaving_count=Count('leaving')
    )


# def get_user_tick_map(tick_list):
#     """
#     конвертирует список отметок в словарь
#     :param tick_list:
#     :return: {user_id: {dt: {C: dttm1,
#                              L: dttm2},
#                         dt2: ...
#                         }
#              ...
#              }
#     """
#     user_dt_type = {}
#     for tick in tick_list:
#         dt = tick.dttm.date()
#         if tick.user_id not in user_dt_type:
#             user_dt_type[tick.user_id] = {}
#         if dt not in user_dt_type[tick.user_id]:
#             user_dt_type[tick.user_id][dt] = {
#                 AttendanceRecords.TYPE_COMING: None,
#                 AttendanceRecords.TYPE_LEAVING: None
#             }
#
#         tick_dttm = user_dt_type[tick.user_id][dt][tick.type]
#         if not tick_dttm \
#             or (tick.type == AttendanceRecords.TYPE_COMING and tick.dttm < tick_dttm) \
#             or (tick.type == AttendanceRecords.TYPE_LEAVING and tick.dttm > tick_dttm):
#                 user_dt_type[tick.user_id][dt][tick.type] = tick.dttm
#
#     return user_dt_type

# def get_user_wd_map(wd_list):
#     """
#     конвертирует список отметок в словарь
#     :param wd_list:
#     :return: {worker_id: {dt: {C: dttm1,
#                              L: dttm2},
#                         dt2: ...
#                         }
#              ...
#              }
#     """
#     user_dt_type = {}
#     for wd in wd_list:
#         if wd.type != WorkerDay.Type.TYPE_WORKDAY.value:
#             continue
#
#         if wd.worker_id not in user_dt_type:
#             user_dt_type[wd.worker_id] = {}
#         if wd.dt not in user_dt_type[wd.worker_id]:
#             user_dt_type[wd.worker_id][wd.dt] = wd
#
#     return user_dt_type


# def working_hours_count(tick_list, wd_list, only_total=False):
#     """
#     :param AttendanceRecords list
#     :return: {user_id: {dt1: working_hours,
#                         dt2: working_hours2,
#                         ...},
#               user_id2: ...
#     """
#     stat = {}
#
#     user_dt_tick = get_user_tick_map(tick_list)
#     user_dt_wd = get_user_wd_map(wd_list)
#     total = 0
#
#     for user_id, dt_wd in user_dt_wd.items():
#         stat[user_id] = {}
#         for dt, wd in dt_wd.items():
#             if user_id in user_dt_tick and dt in user_dt_tick[user_id]:
#                 type_dttm = user_dt_tick[user_id].pop(dt)
#                 stat[user_id][dt] = 0
#
#                 dttm_come = type_dttm[AttendanceRecords.TYPE_COMING]
#                 dttm_leave = type_dttm[AttendanceRecords.TYPE_LEAVING]
#
#                 if not (dttm_come and dttm_leave):
#                     continue
#                 if dttm_come < wd.dttm_work_start:
#                     dttm_come = wd.dttm_work_start
#
#                 if dttm_leave > wd.dttm_work_end:
#                     dttm_leave = wd.dttm_work_end
#
#                 if dttm_come < dttm_leave:
#                     stat[user_id][dt] = (dttm_leave - dttm_come).total_seconds() / 3600
#                     total += stat[user_id][dt]
#
#
#     for user_id, dt_type in user_dt_tick.items():
#         if user_id not in stat:
#             stat[user_id] = {}
#         for dt, type_dttm in dt_type.items():
#             dttm_come = type_dttm[AttendanceRecords.TYPE_COMING]
#             dttm_leave = type_dttm[AttendanceRecords.TYPE_LEAVING]
#
#             if dttm_come and dttm_leave and dttm_come < dttm_leave:
#                 stat[user_id][dt] = (dttm_leave - dttm_come).total_seconds() / 3600
#                 total += stat[user_id][dt]
#     if only_total:
#         return round(total)
#
#     return stat


# def tick_stat_count(tick_list):
#     stat = {
#         'ticks_coming_count': 0,
#         'ticks_leaving_count': 0,
#     }
#
#     user_dt_type = get_user_tick_map(tick_list)
#
#     for dt_type in user_dt_type.values():
#         for type_dttm in dt_type.values():
#             dttm_come = None
#             dttm_leave = None
#             if type_dttm[AttendanceRecords.TYPE_COMING]:
#                 stat['ticks_coming_count'] += 1
#
#             if type_dttm[AttendanceRecords.TYPE_LEAVING]:
#                 stat['ticks_leaving_count'] += 1
#
#     return stat


