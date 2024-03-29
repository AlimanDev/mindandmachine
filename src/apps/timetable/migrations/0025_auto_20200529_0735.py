# Generated by Django 2.2.7 on 2020-05-29 07:35

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0024_merge_20200514_0653'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='workerdaycashboxdetails',
            name='dttm_from',
        ),
        migrations.RemoveField(
            model_name='workerdaycashboxdetails',
            name='dttm_to',
        ),
        migrations.RemoveField(
            model_name='workerdaycashboxdetails',
            name='event',
        ),
        migrations.RemoveField(
            model_name='workerdaycashboxdetails',
            name='is_tablet',
        ),
        migrations.RemoveField(
            model_name='workerdaycashboxdetails',
            name='is_vacancy',
        ),
        migrations.RemoveField(
            model_name='workerdaycashboxdetails',
            name='on_cashbox',
        ),
        migrations.RemoveField(
            model_name='workerdaycashboxdetails',
            name='status',
        ),
        migrations.AlterField(
            model_name='workerday',
            name='worker',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='worker_day', related_query_name='worker_day', to=settings.AUTH_USER_MODEL),
        ),
    ]
