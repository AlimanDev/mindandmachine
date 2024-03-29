# Generated by Django 2.2.16 on 2021-07-14 15:57

from django.db import migrations


def add_permissions(apps, schema_editor):
    FunctionGroup = apps.get_model('base', 'FunctionGroup')
    Group = apps.get_model('base', 'Group')

    func_groups = (
        ('Timesheet', ['GET']),
        ('Timesheet_stats', ['GET']),
        ('Task', ['GET']),
        ('ShopSchedule', ['GET']),
        ('Employee', ['GET']),
        ('AttendanceRecords', ['GET']),
        ('Group', ['GET']),
    )
    groups = Group.objects.all()
    for group in groups:
        for func, methods in func_groups:
            for m in methods:
                FunctionGroup.objects.get_or_create(
                    group=group,
                    method=m,
                    func=func,
                    defaults=dict(
                        access_type='all',
                    )
                )


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0113_auto_20210712_0853'),
    ]

    operations = [
        migrations.RunPython(add_permissions, migrations.RunPython.noop)
    ]
