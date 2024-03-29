# Generated by Django 2.2.16 on 2021-09-14 11:20

from django.db import migrations

def change_report_cron_to_utc(app, schema_editor):
    CrontabSchedule = app.get_model('django_celery_beat', 'CrontabSchedule')
    CrontabSchedule.objects.filter(
        reportconfig__isnull=False,
    ).distinct().update(
        timezone='UTC',
    )

class Migration(migrations.Migration):

    dependencies = [
        ('reports', '0005_auto_20210722_0922'),
    ]

    operations = [
        migrations.RunPython(change_report_cron_to_utc)
    ]
