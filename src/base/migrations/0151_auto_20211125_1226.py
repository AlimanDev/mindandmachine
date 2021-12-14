# Generated by Django 3.2.9 on 2021-11-25 12:26

import re

from django.db import migrations


def shift_schedule_methods_permissions(apps, schema_editor):
    Group = apps.get_model('base', 'Group')
    FunctionGroup = apps.get_model('base', 'FunctionGroup')
    for group in Group.objects.all():
        FunctionGroup.objects.get_or_create(
            group=group,
            func='Employee_shift_schedule',
            method='GET',
            defaults=dict(
                access_type='A',
            ),
        )
        if group and re.search(r'(.*)?админ(.*)?', group.name, re.IGNORECASE) and \
                not re.search(r'(.*)?аутсорс(.*)?', group.name, re.IGNORECASE):
            FunctionGroup.objects.get_or_create(
                group=group,
                func='ShiftSchedule_batch_update_or_create',
                method='POST',
                defaults=dict(
                    access_type='A',
                ),
            )
            FunctionGroup.objects.get_or_create(
                group=group,
                func='ShiftScheduleInterval_batch_update_or_create',
                method='POST',
                defaults=dict(
                    access_type='A',
                ),
            )


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0150_merge_20211124_2147'),
    ]

    operations = [
        migrations.RunPython(shift_schedule_methods_permissions, migrations.RunPython.noop)
    ]
