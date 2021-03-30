from src.timetable.models import PlanAndFactHours, WorkerDay
from datetime import timedelta, datetime
from django.db.models import Q


def get_employee_with_no_ticks(dttm: datetime):
    '''
    Смотрим рабочие дни, с момента начала или окончания прошло не более 5 минут
    '''
    dttm = dttm.replace(second=0, microsecond=0)
    dttm_from = dttm - timedelta(minutes=5)

    no_comming = PlanAndFactHours.objects.filter(
        dttm_work_start_plan__gte=dttm_from, 
        dttm_work_start_plan__lt=dttm, 
        ticks_comming_fact_count=0,
        wd_type=WorkerDay.TYPE_WORKDAY,
    ).select_related(
        'shop',
        'shop__director',
        'worker',
    )

    no_leaving = PlanAndFactHours.objects.filter(
        dttm_work_end_plan__gte=dttm_from, 
        dttm_work_end_plan__lt=dttm, 
        ticks_leaving_fact_count=0,
        wd_type=WorkerDay.TYPE_WORKDAY,
    ).select_related(
        'shop',
        'shop__director',
        'worker',
    )

    return no_comming, no_leaving
    