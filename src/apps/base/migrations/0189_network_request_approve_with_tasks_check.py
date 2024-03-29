# Generated by Django 3.2.9 on 2022-12-13 15:37

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0188_remove_network_run_recalc_fact_from_att_records_on_plan_approve'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='request_approve_with_tasks_check',
            field=models.BooleanField(default=False, help_text='Will create an Event with different code (request_approve_with_tasks)', verbose_name='Request approve: check if employee has any tasks'),
        ),
    ]
