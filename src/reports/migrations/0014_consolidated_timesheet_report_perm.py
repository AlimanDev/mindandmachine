# Создана вручную 2022-06-21 17:56

from django.db import migrations

def add_perm_consolidated_timesheet_report(apps, schema_editor):
    Group = apps.get_model('base', 'Group')
    FunctionGroup = apps.get_model('base', 'FunctionGroup')
    for g in Group.objects.all():
    # for g in Group.objects.filter(code__in=['admin', 'director', 'admin_outsource']):
        FunctionGroup.objects.update_or_create(
            func='Reports_consolidated_timesheet_report',
            method='GET',
            group=g,
            defaults={
                'access_type': 'A',
            }
        )

class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0013_employmentstats'),
    ]

    operations = [
        migrations.RunPython(add_perm_consolidated_timesheet_report, migrations.RunPython.noop),
    ]
