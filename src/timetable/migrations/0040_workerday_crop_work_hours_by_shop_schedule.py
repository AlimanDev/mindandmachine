# Generated by Django 2.2.7 on 2020-11-24 11:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0039_auto_20201119_1353'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerday',
            name='crop_work_hours_by_shop_schedule',
            field=models.BooleanField(default=True, verbose_name='Обрезать рабочие часы по времени работы магазина'),
        ),
    ]