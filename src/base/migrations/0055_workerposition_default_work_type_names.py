# Generated by Django 2.2.7 on 2020-09-09 11:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0032_auto_20200904_0447'),
        ('base', '0054_merge_20200907_0831'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerposition',
            name='default_work_type_names',
            field=models.ManyToManyField(to='timetable.WorkTypeName', verbose_name='Типы работ по умолчанию', blank=True),
        ),
    ]