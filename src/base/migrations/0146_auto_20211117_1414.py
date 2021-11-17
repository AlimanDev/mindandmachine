# Generated by Django 3.2.9 on 2021-11-17 14:14

from django.db import migrations


def disable_removed_task(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(task='src.events.tasks.cron_event').update(enabled=False)


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0145_auto_20211111_1555'),
    ]

    operations = [
        migrations.RunPython(disable_removed_task, migrations.RunPython.noop)
    ]
