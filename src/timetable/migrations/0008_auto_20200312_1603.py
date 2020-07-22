# Generated by Django 2.2.7 on 2020-03-12 16:03

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0007_auto_20200312_0912'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerday',
            name='is_fact',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='workerdayapprove',
            name='dt_from',
            field=models.DateField(default=datetime.datetime(2020, 3, 12, 16, 3, 20, 216530)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='workerdayapprove',
            name='dt_to',
            field=models.DateField(default=datetime.datetime(2020, 3, 12, 16, 3, 40, 457758)),
            preserve_default=False,
        ),
        migrations.RemoveField(
            model_name='workerday',
            name='work_hours',
        ),
        migrations.AddField(
            model_name='workerdayapprove',
            name='is_fact',
            field=models.BooleanField(default=False),
        ),
        migrations.RemoveField(
            model_name='workerdayapprove',
            name='dt_approved',
        ),
   ]