# Generated by Django 2.2.7 on 2020-04-22 11:45

from django.db import migrations, models


def move_vacancy_to_worker_day(apps, schema_editor):
    WorkerDay = apps.get_model('timetable', 'WorkerDay')
    WorkerDayCashboxDetails = apps.get_model('timetable', 'WorkerDayCashboxDetails')
    for vacancy in WorkerDayCashboxDetails.objects.select_related('worker_day', 'work_type').filter(is_vacancy=True, worker_day__isnull=False):
        worker_day = vacancy.worker_day
        worker_day.is_vacancy = True
        worker_day.is_approved = True
        worker_day.shop_id = vacancy.work_type.shop_id
        worker_day.save()
    for vacancy in WorkerDayCashboxDetails.objects.select_related('work_type').filter(is_vacancy=True, worker_day__isnull=True):
        worker_day = WorkerDay.objects.create(
            is_vacancy=True,
            is_approved=True,
            shop_id=vacancy.work_type.shop_id,
            dt=vacancy.dttm_from.date(),
            dttm_work_start=vacancy.dttm_from,
            dttm_work_end=vacancy.dttm_to,
            type=WorkerDay.TYPE_WORKDAY,
        )
        vacancy.worker_day = worker_day
        vacancy.save()
    

class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0018_auto_20200410_1130'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerday',
            name='is_vacancy',
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(move_vacancy_to_worker_day),
    ]
