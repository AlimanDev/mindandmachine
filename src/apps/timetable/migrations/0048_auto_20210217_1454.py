# Generated by Django 2.2.16 on 2021-02-17 14:54

from django.db import migrations
from django.db.models import Case, When, Q, BooleanField


def fill_work_types(apps, schema_editor):
    WorkerDay = apps.get_model('timetable', 'WorkerDay')
    WorkerDayCashboxDetails = apps.get_model('timetable', 'WorkerDayCashboxDetails')
    WorkType = apps.get_model('timetable', 'WorkType')
    EmploymentWorkType = apps.get_model('timetable', 'EmploymentWorkType')
    Employment = apps.get_model('base', 'Employment')

    for fact_wd in WorkerDay.objects.filter(
            is_fact=True, type='W', work_types__isnull=True).select_related('worker__network'):
        plan_wd = WorkerDay.objects.filter(
            type='W',
            worker_id=fact_wd.worker_id,
            dt=fact_wd.dt,
            is_fact=False,
            is_approved=fact_wd.is_approved,
            work_types__isnull=False,
        ).first()
        if plan_wd:
            if fact_wd.shop_id == plan_wd.shop_id:
                WorkerDayCashboxDetails.objects.bulk_create(
                    [
                        WorkerDayCashboxDetails(
                            work_part=details.work_part,
                            worker_day=fact_wd,
                            work_type_id=details.work_type_id,
                        )
                        for details in plan_wd.worker_day_details.all()
                    ]
                )
            else:
                WorkerDayCashboxDetails.objects.bulk_create(
                    [
                        WorkerDayCashboxDetails(
                            work_part=details.work_part,
                            worker_day=fact_wd,
                            work_type=WorkType.objects.filter(shop_id=fact_wd.shop_id,
                                                              work_type_name_id=details.work_type.work_type_name_id).first(),
                        )
                        for details in plan_wd.worker_day_details.select_related('work_type')
                    ]
                )
        elif fact_wd.worker_id:
            active_user_empl = Employment.objects.filter(
                Q(dt_hired__lte=fact_wd.dt) | Q(dt_hired__isnull=True),
                Q(dt_fired__gte=fact_wd.dt) | Q(dt_fired__isnull=True),
                shop__network_id=fact_wd.worker.network_id,
                user__network_id=fact_wd.worker.network_id,
                user_id=fact_wd.worker_id,
            ).annotate(
                is_equal_shops=Case(
                    When(shop_id=fact_wd.shop_id, then=True),
                    default=False, output_field=BooleanField()
                )
            ).order_by('-is_equal_shops').first()
            if active_user_empl:
                employment_work_type = EmploymentWorkType.objects.filter(
                    employment=active_user_empl).order_by('-priority').first()
                if employment_work_type:
                    WorkerDayCashboxDetails.objects.create(
                        work_part=1,
                        worker_day=fact_wd,
                        work_type_id=employment_work_type.work_type_id,
                    )


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0047_auto_20210121_1127'),
    ]

    operations = [
        migrations.RunPython(fill_work_types, migrations.RunPython.noop)
    ]
