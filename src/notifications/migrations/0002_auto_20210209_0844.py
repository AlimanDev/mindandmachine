# Generated by Django 2.2.16 on 2021-02-09 08:44

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0078_auto_20210209_0701'),
        ('django_celery_beat', '0011_auto_20190508_0153'),
        ('notifications', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='eventemailnotification',
            name='cron',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='django_celery_beat.CrontabSchedule', verbose_name='Расписание для отправки'),
        ),
        migrations.AddField(
            model_name='eventemailnotification',
            name='shops',
            field=models.ManyToManyField(blank=True, to='base.Shop', verbose_name='Оповещать по почте магазина'),
        ),
        migrations.AddField(
            model_name='eventonlinenotification',
            name='shops',
            field=models.ManyToManyField(blank=True, to='base.Shop', verbose_name='Оповещать по почте магазина'),
        ),
    ]
