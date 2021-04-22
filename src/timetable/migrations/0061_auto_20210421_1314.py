# Generated by Django 2.2.16 on 2021-04-21 13:14

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0091_auto_20210421_1314'),
        ('timetable', '0060_auto_20210412_0803'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerday',
            name='employee',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='employees', to='base.Employee', verbose_name='Сотрудник'),
        ),
        migrations.AlterUniqueTogether(
            name='workerday',
            unique_together={('dt', 'employee', 'is_fact', 'is_approved')},
        ),
    ]
