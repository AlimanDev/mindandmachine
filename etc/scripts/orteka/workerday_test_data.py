import datetime
from src.base.models import Employment
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails, WorkType
from django.db.models import Q
import random


def fill_data_test(shop_ids, work_type_name, dt_start, dt_end, is_fact=False, is_approved=True, delete_curr_version=False):
    employments = Employment.objects.filter(
        Q(dt_fired__isnull=True) | Q(dt_fired__gte=dt_start),
        shop_id__in=shop_ids,
    )

    curr_data = WorkerDay.objects.filter(
        dt__gte=dt_start,
        dt__lte=dt_end,
        employee_id__in=[e.employee_id for e in employments],
        is_fact=is_fact,
        is_approved=is_approved,
    )
    if curr_data.count():
        if delete_curr_version:
            WorkerDayCashboxDetails.objects.filter(
                worker_day__in=curr_data
            ).delete()
            curr_data.delete()
        else:
            raise ValueError(f'there are {curr_data.count()} workerdays in database.')

    circle_period = 6
    for empl in employments:
        work_type, _ = WorkType.objects.get_or_create(shop_id=empl.shop_id, work_type_name=work_type_name)
        empl_dt = dt_start
        ind = random.randint(0, circle_period)
        while empl_dt <= dt_end:
            ind = (ind + 1) % circle_period
            if ind in [0, 1]:
                if not is_fact:
                    wd = WorkerDay.objects.create(
                        dt=empl_dt,
                        employee_id=empl.employee_id,
                        employment=empl,
                        type=WorkerDay.TYPE_HOLIDAY,
                        shop_id=empl.shop_id,
                        is_fact=is_fact,
                        is_approved=is_approved,
                    )
            else:
                wd = WorkerDay.objects.create(
                    dt=empl_dt,
                    dttm_work_start=datetime.datetime.combine(empl_dt, datetime.time(10)),
                    dttm_work_end=datetime.datetime.combine(empl_dt, datetime.time(20)),
                    employee_id=empl.employee_id,
                    employment=empl,
                    type=WorkerDay.TYPE_WORKDAY,
                    shop_id=empl.shop_id,
                    is_fact=is_fact,
                    is_approved=is_approved,
                )

                WorkerDayCashboxDetails.objects.create(
                    worker_day=wd,
                    work_type=work_type,
                )

            empl_dt = empl_dt + datetime.timedelta(days=1)



def delete_workerdays(shop_ids, dt_start, dt_end, is_fact=False, is_approved=True):
    WorkerDay.objects_with_excluded.filter(
        dt__gte=dt_start,
        dt__lte=dt_end,
        shop_id__in=shop_ids,
        is_fact=is_fact,
        is_approved=is_approved,
    ).delete()