# Создано вручную 2022-08-23 13:53

from django.db import migrations

def create_or_update_view_v_plan_and_fact_hours_2y(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0117_auto_20220321_0923'),
    ]

    operations = [
        migrations.RunPython(create_or_update_view_v_plan_and_fact_hours_2y, migrations.RunPython.noop),
    ]
