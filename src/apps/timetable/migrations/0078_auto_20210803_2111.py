# Generated by Django 2.2.16 on 2021-08-03 21:11
from datetime import timedelta

from django.db import migrations
from django.db.models import OuterRef, Subquery
from django.utils import timezone


def fill_closest_plan_approved(apps, schema_editor):
    dt_now = timezone.now().date()
    WorkerDay = apps.get_model('timetable', 'WorkerDay')
    WorkerDay.objects.filter(closest_plan_approved__isnull=False).update(closest_plan_approved=None)
    WorkerDay.objects.filter(
        dt__gte=dt_now - timedelta(days=180),
        is_fact=True,
        is_approved=True,
    ).update(
        closest_plan_approved=Subquery(
            WorkerDay.objects.filter(
                employee_id=OuterRef('employee_id'),
                shop_id=OuterRef('shop_id'),
                type=OuterRef('type'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=True,
            ).values('id')[:1],
        )
    )


class Migration(migrations.Migration):
    dependencies = [
        ('timetable', '0077_auto_20210803_2020'),
    ]

    operations = [
        migrations.RunPython(fill_closest_plan_approved, migrations.RunPython.noop),
    ]
