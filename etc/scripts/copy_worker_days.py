from django.db import models, transaction
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails


def copy_approved(dt_from, dt_to=None):
    dt_filter = {
        'dt__gte': dt_from,
    }
    if dt_to:
        dt_filter['dt__lte'] = dt_to
    with transaction.atomic():
        not_approved_subq = WorkerDay.objects_with_excluded.filter(
            employee_id=models.OuterRef('employee_id'),
            dt=models.OuterRef('dt'),
            is_approved=False,
            is_fact=models.OuterRef('is_fact'),
        )
        worker_days_to_copy = list(WorkerDay.objects_with_excluded.filter(
            employee__isnull=False,
            **dt_filter,
        ).annotate(
            not_approved_exist=models.Exists(not_approved_subq),
        ).filter(
            not_approved_exist=False,
        ).select_related(
            'employment', 
            'employment__position',
            'employment__position__breaks',
            'shop',
            'shop__settings',
            'shop__settings__breaks',
            'shop__network',
            'shop__network__breaks',
        ).prefetch_related(
            'worker_day_details',
        ))
        wds = [
            WorkerDay(
                shop=wd.shop,
                employee_id=wd.employee_id,
                employment=wd.employment,
                dttm_work_start=wd.dttm_work_start,
                dttm_work_end=wd.dttm_work_end,
                dt=wd.dt,
                is_fact=wd.is_fact,
                is_approved=False,
                type=wd.type,
                created_by_id=wd.created_by_id, # нужно ли это копировать?
                last_edited_by_id=wd.last_edited_by_id, # и это
                is_vacancy=wd.is_vacancy,
                is_outsource=wd.is_outsource,
                comment=wd.comment,
                canceled=wd.canceled,
                need_count_wh=True,
            )
            for wd in worker_days_to_copy
        ]
        wds = WorkerDay.objects.bulk_create(wds)
        search_wds = {}
        for wd in wds:
            key_employee = wd.employee_id
            search_wds.setdefault(key_employee, {}).setdefault(wd.dt, {})[wd.is_fact] = wd

        WorkerDayCashboxDetails.objects.bulk_create(
            [
                WorkerDayCashboxDetails(
                    work_part=details.work_part,
                    worker_day=search_wds[wd.employee_id][wd.dt][wd.is_fact],
                    work_type_id=details.work_type_id,
                )
                for wd in worker_days_to_copy
                for details in wd.worker_day_details.all()
            ]
        )
