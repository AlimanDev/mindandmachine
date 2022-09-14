# Generated by Django 2.2.16 on 2021-02-25 12:23

from django.db import migrations


def create_or_replace_plan_and_fact_hours(apps, schema_editor):
    pass


def create_or_replace_timetable_plan_and_fact_hours(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('timetable', '0048_auto_20210217_1454'),
    ]

    operations = [
        migrations.RunPython(create_or_replace_plan_and_fact_hours, migrations.RunPython.noop),
        migrations.RunPython(create_or_replace_timetable_plan_and_fact_hours, migrations.RunPython.noop),
    ]
