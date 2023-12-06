# Generated by Django 2.2.16 on 2021-09-06 15:53

from django.db import migrations


def add_worker_day_batch_update_or_create_perms(apps, schema_editor):
    Group = apps.get_model('base', 'Group')
    FunctionGroup = apps.get_model('base', 'FunctionGroup')
    groups_qs = Group.objects.filter(
        id__in=FunctionGroup.objects.filter(
            func='WorkerDay',
            method__in=['PUT', 'POST'],
        ).values_list('group_id', flat=True)
    )
    for group in groups_qs:
        FunctionGroup.objects.get_or_create(
            group=group,
            func='WorkerDay_batch_update_or_create',
            method='POST',
            defaults=dict(
                access_type='A',
            )
        )


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0087_auto_20210903_1153'),
    ]

    operations = [
        migrations.RunPython(add_worker_day_batch_update_or_create_perms, migrations.RunPython.noop),
    ]