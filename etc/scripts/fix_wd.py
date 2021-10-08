from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q, OuterRef, Subquery, F
from django.db.utils import IntegrityError

from src.base.models import Employment
from src.timetable.models import WorkerDay, AttendanceRecords


def fix_wd_employments():
    WorkerDay.objects.filter(
        Q(employment__isnull=True) |
        Q(Q(dt__lt=F('employment__dt_hired')) | Q(dt__gt=F('employment__dt_fired'))),
    ).update(
        employment_id=Subquery(Employment.objects.get_active_empl_by_priority(
            dt=OuterRef('dt'),
            employee_id=OuterRef('employee_id'),
            norm_work_hours__gt=0,
        ).values('id')[:1]),
    )


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
