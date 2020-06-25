# Generated by Django 2.2.7 on 2020-04-24 15:26

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0019_workerday_is_vacancy'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workerday',
            name='worker',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
    ]
