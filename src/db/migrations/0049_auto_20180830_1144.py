# Generated by Django 2.0.5 on 2018-08-27 12:38

from django.db import migrations, models
from datetime import datetime, timedelta


def change_tm_to_dttm(apps, schema_editor):
    WorkerDay = apps.get_model('db', 'WorkerDay')
    WorkerDayCashboxDetails = apps.get_model('db', 'WorkerDayCashboxDetails')

    workerdays = WorkerDay.objects.all()

    for day in workerdays:
        if day.tm_work_start:
            day.dttm_work_start = datetime.combine(day.dt, day.tm_work_start)

        if day.tm_work_end:
            if day.tm_work_start and day.tm_work_start > day.tm_work_end:
                day.dttm_work_end = datetime.combine(day.dt + timedelta(days=1), day.tm_work_end)
            else:
                day.dttm_work_end = datetime.combine(day.dt, day.tm_work_end)
        day.save()

    details = WorkerDayCashboxDetails.objects.all()
    for detail in details:
        if detail.tm_from:
            detail.dttm_from = datetime.combine(detail.worker_day.dt, detail.tm_from)

        if detail.tm_to:
            if detail.tm_from and detail.tm_from > detail.tm_to:
                detail.dttm_to = datetime.combine(detail.worker_day.dt + timedelta(days=1), detail.tm_to)
            else:
                detail.dttm_to = datetime.combine(detail.worker_day.dt, detail.tm_to)
        detail.save()


class Migration(migrations.Migration):
    dependencies = [
        ('db', '0048_merge_20180820_1453'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerday',
            name='dttm_work_end',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='workerday',
            name='dttm_work_start',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='workerdaycashboxdetails',
            name='dttm_from',
            field=models.DateTimeField(default=datetime(2000, 1, 1, 0, 0)),
        ),
        migrations.AddField(
            model_name='workerdaycashboxdetails',
            name='dttm_to',
            field=models.DateTimeField(blank=True, null=True),
        ),

        migrations.RunPython(change_tm_to_dttm),



    ]
