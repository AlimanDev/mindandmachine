from src.timetable.models import PlanAndFactHours, WorkerDay
from datetime import timedelta, datetime
from src.base.models import Shop


def get_worker_days_with_no_ticks(dttm: datetime):
    '''
    Смотрим рабочие дни, с момента начала или окончания прошло не более 5 минут
    '''
    dttm = dttm.replace(second=0, microsecond=0)

    no_comming = []
    no_leaving = []

    for shop in Shop.objects.all():
        dttm_to = dttm + timedelta(hours=shop.get_tz_offset())
        dttm_from = dttm_to - timedelta(minutes=5)
        no_comming.extend(
            list(
                PlanAndFactHours.objects.filter(
                    dttm_work_start_plan__gte=dttm_from, 
                    dttm_work_start_plan__lt=dttm_to, 
                    ticks_comming_fact_count=0,
                    wd_type=WorkerDay.TYPE_WORKDAY,
                    shop=shop,
                ).select_related(
                    'shop',
                    'shop__director',
                    'worker',
                )
            )
        )
        no_leaving.extend(
            list(
                PlanAndFactHours.objects.filter(
                    dttm_work_end_plan__gte=dttm_from, 
                    dttm_work_end_plan__lt=dttm_to, 
                    ticks_leaving_fact_count=0,
                    wd_type=WorkerDay.TYPE_WORKDAY,
                    shop=shop,
                ).select_related(
                    'shop',
                    'shop__director',
                    'worker',
                )
            )
        )
    return no_comming, no_leaving
    