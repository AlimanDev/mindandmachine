# Generated by Django 2.2.16 on 2021-05-19 08:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0071_auto_20210517_2043'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancerecords',
            name='terminal',
            field=models.BooleanField(default=False, help_text='Отметка с теримнала'),
        ),
    ]
