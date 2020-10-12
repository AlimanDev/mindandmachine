import json
from datetime import timedelta

from django.db.models import (
    Count, F, Sum, Min, Max, Q, Case, When, Value, IntegerField, DateTimeField, FloatField)
from django.db.models.functions import Extract, Coalesce, Cast, Ceil

from src.timetable.models import (
    AttendanceRecords,
    WorkerDay
)
from src.base.models import Break


def wd_stat_count(worker_days, shop):
    # break_triplets = json.loads(shop.settings.break_triplets) if shop.settings else []
    break_triplets = {
        b.id: list(map(lambda x: (x[0] / 60, x[1] / 60, sum(x[2]) / 60), b.breaks))
        for b in Break.objects.filter(network_id=shop.network_id)
    }
    breaktime_plan = Value(0, output_field=FloatField())
    breaktime_fact = Value(0, output_field=FloatField())
    if break_triplets:
        whens = [
            When(
                Q(hours_plan_0__gte=break_triplet[0], hours_plan_0__lte=break_triplet[1]) & 
                (Q(employment__position__breaks_id=break_id) | (Q(employment__position__breaks__isnull=True) & Q(employment__shop__settings__breaks_id=break_id))),
                then=break_triplet[2]
            )
            for break_id, breaks in break_triplets.items()
            for break_triplet in breaks
        ]
        breaktime_plan = Case(*whens, output_field=FloatField())
        whens = [
            When(
                Q(hours_fact_0__gte=break_triplet[0], hours_fact_0__lte=break_triplet[1]) & 
                (Q(employment__position__breaks_id=break_id) | (Q(employment__position__breaks__isnull=True) & Q(employment__shop__settings__breaks_id=break_id))),
                then = break_triplet[2])
            for break_id, breaks in break_triplets.items()
            for break_triplet in breaks
        ]
        breaktime_fact = Case(*whens, output_field=FloatField())

    return worker_days.filter(
        type=WorkerDay.TYPE_WORKDAY
    ).values('worker_id','employment_id', 'dt', 'dttm_work_start','dttm_work_end').annotate(
        coming=Min('worker__attendancerecords__dttm', filter=Q(
            worker__attendancerecords__shop=shop,
            worker__attendancerecords__dttm__date=F('dt'),
            worker__attendancerecords__type=AttendanceRecords.TYPE_COMING,
        )),
        leaving=Max('worker__attendancerecords__dttm', filter=Q(
            worker__attendancerecords__shop=shop,
            worker__attendancerecords__dttm__date=F('dt'),
            worker__attendancerecords__type=AttendanceRecords.TYPE_LEAVING)),
        is_late=Case(
            When(coming__gt=F('dttm_work_start')-timedelta(minutes=15), then=1),
            default=Value(0), output_field=IntegerField()),
        hours_plan_0=Cast(Extract(F('dttm_work_end') - F('dttm_work_start'), 'epoch') / 3600, FloatField()),
        hours_fact_0=Cast(
            Extract(
                Coalesce(
                    Case(When(leaving__gt=F('dttm_work_end'), then=F('dttm_work_end')),
                            default=F('leaving'), output_field=DateTimeField())
                    -
                    Case(When(coming__lt=F('dttm_work_start'), then=F('dttm_work_start')),
                        default=F('coming'), output_field=DateTimeField()),
                    timedelta(hours=0)),
                'epoch') / 3600,
            FloatField()),
        hours_fact=Ceil(F('hours_fact_0') - breaktime_fact),
        hours_plan=Ceil(F('hours_plan_0') - breaktime_plan)
    )


def wd_stat_count_total(worker_days, shop):
    return wd_stat_count(worker_days, shop).aggregate(
         hours_count_fact=Sum('hours_fact'),
         hours_count_plan=Sum('hours_plan'),
         lateness_count=Sum('is_late'),
         ticks_coming_count=Count('coming'),
         ticks_leaving_count=Count('leaving')
    )
