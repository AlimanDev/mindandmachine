# Generated by Django 2.2.16 on 2021-11-09 05:47

from django.db import migrations

def replace_view_plan_and_fact_hours(apps, schema_editor):
    schema_editor.execute("""
        DROP VIEW IF EXISTS timetable_plan_and_fact_hours CASCADE;
    """)

class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0094_auto_20211101_1555'),
    ]

    operations = [
        migrations.RunPython(replace_view_plan_and_fact_hours, migrations.RunPython.noop)
    ]
