# Generated by Django 2.2.7 on 2020-01-10 12:36

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0002_alterfield'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerday',
            name='dttm_deleted',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='workerdaychangerequest',
            name='dttm_deleted',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='workerday',
            name='dttm_added',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='workerdaycashboxdetails',
            name='dttm_added',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name='workerdaychangerequest',
            name='dttm_added',
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]