# Generated by Django 2.2.16 on 2021-11-01 15:55

from datetime import timedelta, date

from django.db import migrations
from django.db.models import OuterRef, Subquery, Count, IntegerField, Q


def fix_closest_plan_approved(apps, schema_editor):
    Network = apps.get_model('base', 'Network')
    delta_in_secs = 60 * 60 * 5
    Network.objects.all().update(
        set_closest_plan_approved_delta_for_manual_fact=delta_in_secs,
        max_work_shift_seconds=(60 * 60 * 23) + (59 * 60),
        max_plan_diff_in_seconds=60 * 60 * 7,
    )
    WorkerDay = apps.get_model('timetable', 'WorkerDay')
    qs = WorkerDay.objects.filter(
        dt__gte=date(2021, 10, 1),
        is_fact=True,
        closest_plan_approved__isnull=True,
    ).annotate(
        plan_approved_count=Subquery(WorkerDay.objects.filter(
            employee_id=OuterRef('employee_id'),
            dt=OuterRef('dt'),
            is_fact=False,
            is_approved=True,
            type__is_dayoff=False,
        ).values(
            'employee_id',
            'dt',
            'is_fact',
            'is_approved',
        ).annotate(
            objs_count=Count('*'),
        ).values('objs_count')[:1], output_field=IntegerField())
    )

    qs.filter(plan_approved_count__gt=1).update(
        closest_plan_approved_id=Subquery(WorkerDay.objects.filter(
            Q(dttm_work_start__gte=OuterRef('dttm_work_start') - timedelta(seconds=delta_in_secs)) &
            Q(dttm_work_start__lte=OuterRef('dttm_work_start') + timedelta(seconds=delta_in_secs)) &
            Q(dttm_work_end__gte=OuterRef('dttm_work_end') - timedelta(seconds=delta_in_secs)) &
            Q(dttm_work_end__lte=OuterRef('dttm_work_end') + timedelta(seconds=delta_in_secs)),
            employee_id=OuterRef('employee_id'),
            dt=OuterRef('dt'),
            is_fact=False,
            is_approved=True,
            type__is_dayoff=False,
        ).values('id')[:1])
    )
    qs.filter(plan_approved_count=1).update(
        closest_plan_approved_id=Subquery(WorkerDay.objects.filter(
            employee_id=OuterRef('employee_id'),
            dt=OuterRef('dt'),
            is_fact=False,
            is_approved=True,
            type__is_dayoff=False,
        ).values('id')[:1])
    )


class Migration(migrations.Migration):
    dependencies = [
        ('timetable', '0093_auto_20211020_1216'),
    ]

    operations = [
        migrations.RunPython(fix_closest_plan_approved, migrations.RunPython.noop),
    ]
