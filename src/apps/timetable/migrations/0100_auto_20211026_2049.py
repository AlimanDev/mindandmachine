# Generated by Django 2.2.24 on 2021-10-26 20:49

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0099_auto_20211022_0827'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='workerday',
            name='unique_dt_employee_is_fact_is_approved_if_not_workday',
        ),
    ]
