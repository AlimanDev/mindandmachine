# Generated by Django 2.0.5 on 2018-08-21 18:00

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0046_auto_20180821_1550'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='workerdaychangelog',
            name='changed_by',
        ),
        migrations.RemoveField(
            model_name='workerdaychangelog',
            name='worker_day',
        ),
        migrations.RemoveField(
            model_name='workerdaychangelog',
            name='worker_day_worker',
        ),
        migrations.AddField(
            model_name='workerday',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='user_created', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='workerday',
            name='parent_worker_day',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='child', to='db.WorkerDay'),
        ),
        migrations.AlterUniqueTogether(
            name='workerday',
            unique_together=set(),
        ),
        migrations.DeleteModel(
            name='WorkerDayChangeLog',
        ),
    ]
