# Generated by Django 2.2.7 on 2020-04-30 14:05

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0021_merge_20200429_1334'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workerday',
            name='worker',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='worker_day', related_query_name='worker_day', to=settings.AUTH_USER_MODEL),
        ),
    ]
