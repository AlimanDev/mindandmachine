# Generated by Django 2.2.24 on 2021-10-14 00:25

from decimal import Decimal
from django.db import migrations, models
import django.db.models.deletion
import src.util.mixins.bulk_update_or_create


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0139_auto_20211013_2310'),
        ('timetable', '0091_auto_20210930_1556'),
    ]

    operations = [
        migrations.CreateModel(
            name='TimesheetItem',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('timesheet_type', models.CharField(choices=[('F', 'Фактический'), ('M', 'Основной'), ('A', 'Дополнительный')], max_length=32, verbose_name='Тип табеля')),
                ('dt', models.DateField()),
                ('hours_type', models.CharField(blank=True, choices=[('D', 'Явился и трудился в дневное время'), ('N', 'Работал в ночное время')], help_text='Актуально для рабочих типов дней', max_length=32, null=True, verbose_name='Тип времени')),
                ('hours', models.DecimalField(decimal_places=2, default=Decimal('0.00'), max_digits=4)),
                ('source', models.CharField(blank=True, choices=[('P', 'Planned timetable'), ('F', 'Attendance records'), ('M', 'Manual changes'), ('S', 'Determined by the system')], max_length=12, verbose_name='Источник данных')),
                ('day_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='timetable.WorkerDayType', verbose_name='Тип дня')),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='base.Employee', verbose_name='Сотрудник')),
                ('position', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='base.WorkerPosition', verbose_name='Должность')),
                ('shop', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Shop', verbose_name='Поздразделение выхода сотрудника')),
                ('work_type_name', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='timetable.WorkTypeName', verbose_name='Тип работ')),
            ],
            options={
                'verbose_name': 'Запись в табеле',
                'verbose_name_plural': 'Записи в табеле',
            },
            bases=(src.util.mixins.bulk_update_or_create.BatchUpdateOrCreateModelMixin, models.Model),
        ),
    ]
