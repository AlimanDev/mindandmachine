# Generated by Django 2.2.16 on 2021-06-02 22:55

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0106_auto_20210601_1438'),
        ('timetable', '0071_auto_20210517_2043'),
    ]

    operations = [
        migrations.CreateModel(
            name='Timesheet',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('dt', models.DateField(verbose_name='Дата')),
                ('fact_timesheet_source', models.CharField(blank=True, choices=[('plan', 'Planned timetable'), ('fact', 'Attendance records'), ('manual', 'Manual changes'), ('system', 'Determined by the system')], max_length=12, verbose_name='Источник данных для фактического табеля')),
                ('fact_timesheet_type', models.CharField(choices=[('H', 'Выходной'), ('W', 'Рабочий день'), ('V', 'Отпуск'), ('S', 'Больничный лист'), ('Q', 'Квалификация'), ('A', 'Неявка до выяснения обстоятельств'), ('M', 'Б/л по беременноси и родам'), ('T', 'Командировка'), ('O', 'Другое'), ('D', 'Удален'), ('E', 'Пусто'), ('HW', 'Работа в выходной день'), ('RA', 'Прогул на основании акта'), ('EV', 'Доп. отпуск'), ('SV', 'Учебный отпуск'), ('TV', 'Отпуск за свой счёт'), ('ST', 'Отпуск за свой счёт по уважительной причине'), ('G', 'Гос. обязанности'), ('HS', 'Спец. выходной'), ('MC', 'Отпуск по уходу за ребёнком до 3-х лет'), ('C', 'Выходные дни по уходу')], max_length=2)),
                ('fact_timesheet_dttm_work_start', models.DateTimeField(blank=True, null=True)),
                ('fact_timesheet_dttm_work_end', models.DateTimeField(blank=True, null=True)),
                ('fact_timesheet_total_hours', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('fact_timesheet_day_hours', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('fact_timesheet_night_hours', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('main_timesheet_type', models.CharField(blank=True, choices=[('H', 'Выходной'), ('W', 'Рабочий день'), ('V', 'Отпуск'), ('S', 'Больничный лист'), ('Q', 'Квалификация'), ('A', 'Неявка до выяснения обстоятельств'), ('M', 'Б/л по беременноси и родам'), ('T', 'Командировка'), ('O', 'Другое'), ('D', 'Удален'), ('E', 'Пусто'), ('HW', 'Работа в выходной день'), ('RA', 'Прогул на основании акта'), ('EV', 'Доп. отпуск'), ('SV', 'Учебный отпуск'), ('TV', 'Отпуск за свой счёт'), ('ST', 'Отпуск за свой счёт по уважительной причине'), ('G', 'Гос. обязанности'), ('HS', 'Спец. выходной'), ('MC', 'Отпуск по уходу за ребёнком до 3-х лет'), ('C', 'Выходные дни по уходу')], max_length=2)),
                ('main_timesheet_total_hours', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('main_timesheet_day_hours', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('main_timesheet_night_hours', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('additional_timesheet_hours', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='base.Employee', verbose_name='Сотрудник')),
                ('shop', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='base.Shop', verbose_name='Поздразделение')),
            ],
            options={
                'verbose_name': 'Запись в табеле',
                'verbose_name_plural': 'Записи в табеле',
                'unique_together': {('dt', 'employee')},
            },
        ),
    ]
