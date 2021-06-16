# Generated by Django 2.2.16 on 2021-05-24 11:57

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('forecast', '0038_auto_20210423_0841'),
        ('base', '0102_auto_20210520_1912'),
    ]

    operations = [
        migrations.CreateModel(
            name='Task',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('dttm_added', models.DateTimeField(default=django.utils.timezone.now)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('code', models.CharField(blank=True, max_length=128, null=True, unique=True)),
                ('dt', models.DateField(help_text='По умолчанию берется из времени начала', verbose_name='Дата, к которой относится задача (для ночных смен)')),
                ('dttm_start_time', models.DateTimeField(verbose_name='Время начала')),
                ('dttm_end_time', models.DateTimeField(verbose_name='Время окончания')),
                ('dttm_event', models.DateTimeField(blank=True, null=True, verbose_name='Время события создания/изменения объекта')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='base.Employee', verbose_name='Сотрудник')),
                ('operation_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='forecast.OperationType')),
            ],
            options={
                'verbose_name': 'Задача',
                'verbose_name_plural': 'Задачи',
            },
        ),
    ]