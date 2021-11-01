# Generated by Django 2.2.16 on 2021-10-15 09:11

import datetime
from django.db import migrations, models

def create_perm_for_schedule_devation_report(apps, schema_editor):
    Group = apps.get_model('base', 'Group')
    FunctionGroup = apps.get_model('base', 'FunctionGroup')

    groups = Group.objects.all()

    for g in groups:
        FunctionGroup.objects.get_or_create(
            func='Reports_schedule_deviation',
            group=g,
            method='GET',
            defaults={
                'access_type': 'A',
            }
        )


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0139_auto_20211014_0611'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='allowed_interval_for_early_arrival',
            field=models.DurationField(default=datetime.timedelta(0), verbose_name='Allowed interval for early arrival'),
        ),
        migrations.AddField(
            model_name='network',
            name='allowed_interval_for_late_departure',
            field=models.DurationField(default=datetime.timedelta(0), verbose_name='Allowed interval for late departure'),
        ),
        migrations.RunPython(create_perm_for_schedule_devation_report, migrations.RunPython.noop),
    ]