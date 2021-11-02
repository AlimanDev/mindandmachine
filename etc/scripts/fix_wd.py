from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q, OuterRef, F, Exists, Prefetch
from django.db.utils import IntegrityError

from src.timetable.models import WorkType, WorkerDay, AttendanceRecords, WorkerDayCashboxDetails


def fix_plan_night_shifts(**kwargs):
    wdays = WorkerDay.objects.filter(
        Q(dttm_work_end_tabel__lt=F('dttm_work_start_tabel')) |
        Q(dttm_work_end__lt=F('dttm_work_start')),
        is_fact=False,
        **kwargs,
    )
    fixed_count = 0
    for wd in wdays:
        if wd.dttm_work_start > wd.dttm_work_end:
            fixed_count += 1
            wd.dttm_work_end = datetime.combine(wd.dt + timedelta(days=1), wd.dttm_work_end.time())
            wd.save()
    print(fixed_count)


def fix_wrong_att_records(**kwargs):
    wdays = WorkerDay.objects.filter(
        Q(dttm_work_end_tabel__lt=F('dttm_work_start_tabel')) |
        Q(dttm_work_end__lt=F('dttm_work_start')),
        is_fact=True,
        last_edited_by__isnull=True,
        **kwargs
    )
    fixed_count = 0
    for wd in wdays:
        if wd.dt != wd.dttm_work_start.date():
            att_record_coming = AttendanceRecords.objects.filter(
                dttm=wd.dttm_work_start,
                type=AttendanceRecords.TYPE_COMING,
                employee_id=wd.employee_id,
            ).first()
            att_record_leaving = AttendanceRecords.objects.filter(
                dttm=wd.dttm_work_end,
                type=AttendanceRecords.TYPE_LEAVING,
                employee_id=wd.employee_id,
            ).first()
            if att_record_coming and att_record_leaving:
                new_dt = wd.dttm_work_start.date()
                try:
                    with transaction.atomic():
                        wd.dt = new_dt
                        wd.save()
                        AttendanceRecords.objects.filter(id=att_record_coming.id).update(dt=new_dt)
                        AttendanceRecords.objects.filter(id=att_record_leaving.id).update(dt=new_dt)
                    fixed_count += 1
                except IntegrityError as e:
                    print(f'wd id={str(wd.id)}')
                    print(f'IntegrityError: {str(e)}')

    print(fixed_count)


def fix_wrong_work_types(**kwargs):
    worker_days = WorkerDay.objects.filter(**kwargs).annotate(
        cashbox_details=Exists(
            WorkerDayCashboxDetails.objects.filter(
                worker_day_id=OuterRef('pk'),
            )
        ),
        cashbox_details_not_same_shop=Exists(
            WorkerDayCashboxDetails.objects.filter(
                worker_day_id=OuterRef('pk'),
            ).exclude(
                work_type__shop_id=OuterRef('shop_id'),
            )
        )
    ).filter(
        cashbox_details=True,
        cashbox_details_not_same_shop=True,
    ).prefetch_related(Prefetch('worker_day_details', queryset=WorkerDayCashboxDetails.objects.select_related('work_type')))

    work_types = {}
    for wt in WorkType.objects.filter(shop_id__in=worker_days.values_list('shop_id', flat=True)):
        work_types.setdefault(wt.shop_id, {})[wt.work_type_name_id] = wt
    
    details_to_update = []
    for wd in worker_days:
        for detail in wd.worker_day_details.all():
            if detail.work_type.shop_id != wd.shop_id:
                shop_work_types = work_types.get(wd.shop_id)
                if not shop_work_types:
                    print(f'WARN: {wd.shop} has no work types')
                    continue
                work_type = shop_work_types.get(detail.work_type.work_type_name_id)
                if not work_type:
                    print(f'WARN: {wd.shop} has no work type {detail.work_type.work_type_name}')
                    work_type = list(shop_work_types.values())[0]
                detail.work_type = work_type
                details_to_update.append(detail)

    WorkerDayCashboxDetails.objects.bulk_update(
        details_to_update,
        fields=['work_type'],
    )
    print(f'fixed {len(details_to_update)} work types')
