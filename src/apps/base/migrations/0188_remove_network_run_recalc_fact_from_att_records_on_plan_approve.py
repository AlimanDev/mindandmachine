# Generated by Django 3.2.9 on 2022-11-18 11:30

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0187_alter_network_allowed_interval_for_late_departure'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='network',
            name='run_recalc_fact_from_att_records_on_plan_approve',
        ),
    ]
