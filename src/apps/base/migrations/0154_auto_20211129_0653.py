# Generated by Django 3.2.9 on 2021-11-29 06:53

from django.db import migrations

def delete_unused_tasks(apps, schema_editor):
    PeriodicTask = apps.get_model('django_celery_beat', 'PeriodicTask')
    PeriodicTask.objects.filter(
        name__in=[
            'task-every-30-min-update-queue',
            'task-free-all-workers-after-shop-closes',
            'task-allocation-of-time-for-work-on-cashbox',
            'task-clean-camera-stats',
            'task-update-visitors-info',
            'task-update-operation-templates',
            'task-trigger-cron-event',
        ]
    ).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('base', '0153_network_show_cost_for_inner_vacancies'),
    ]

    operations = [
        migrations.RunPython(delete_unused_tasks, migrations.RunPython.noop),
    ]