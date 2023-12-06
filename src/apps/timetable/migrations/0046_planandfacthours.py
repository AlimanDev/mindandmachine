# Generated by Django 2.2.7 on 2021-01-20 11:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0045_planandfacthours'),
        ('base', '0076_auto_20210120_1223'),
    ]

    operations = [
        migrations.CreateModel(
            name='PlanAndFactHours',
            fields=[
                ('id', models.CharField(max_length=256, primary_key=True, serialize=False)),
                ('dt', models.DateField()),
                ('shop_name', models.CharField(max_length=512)),
                ('shop_code', models.CharField(max_length=512)),
                ('wd_type', models.CharField(choices=[('H', 'Выходной'), ('W', 'Рабочий день'), ('V', 'Отпуск'), ('S', 'Больничный лист'), ('Q', 'Квалификация'), ('A', 'Неявка до выяснения обстоятельств'), ('M', 'Б/л по беременноси и родам'), ('T', 'Командировка'), ('O', 'Другое'), ('D', 'Удален'), ('E', 'Пусто'), ('HW', 'Работа в выходной день'), ('RA', 'Прогул на основании акта'), ('EV', 'Доп. отпуск'), ('SV', 'Учебный отпуск'), ('TV', 'Отпуск за свой счёт'), ('ST', 'Отпуск за свой счёт по уважительной причине'), ('G', 'Гос. обязанности'), ('HS', 'Спец. выходной'), ('MC', 'Отпуск по уходу за ребёнком до 3-х лет'), ('C', 'Выходные дни по уходу')], max_length=4)),
                ('worker_fio', models.CharField(choices=[('H', 'Выходной'), ('W', 'Рабочий день'), ('V', 'Отпуск'), ('S', 'Больничный лист'), ('Q', 'Квалификация'), ('A', 'Неявка до выяснения обстоятельств'), ('M', 'Б/л по беременноси и родам'), ('T', 'Командировка'), ('O', 'Другое'), ('D', 'Удален'), ('E', 'Пусто'), ('HW', 'Работа в выходной день'), ('RA', 'Прогул на основании акта'), ('EV', 'Доп. отпуск'), ('SV', 'Учебный отпуск'), ('TV', 'Отпуск за свой счёт'), ('ST', 'Отпуск за свой счёт по уважительной причине'), ('G', 'Гос. обязанности'), ('HS', 'Спец. выходной'), ('MC', 'Отпуск по уходу за ребёнком до 3-х лет'), ('C', 'Выходные дни по уходу')], max_length=512)),
                ('fact_work_hours', models.DecimalField(decimal_places=2, max_digits=4)),
                ('plan_work_hours', models.DecimalField(decimal_places=2, max_digits=4)),
                ('late_arrival', models.PositiveSmallIntegerField()),
                ('early_departure', models.PositiveSmallIntegerField()),
                ('is_vacancy', models.BooleanField()),
                ('ticks_fact_count', models.PositiveSmallIntegerField()),
                ('ticks_plan_count', models.PositiveSmallIntegerField()),
                ('worker_username', models.CharField(max_length=512)),
                ('work_type_name', models.CharField(max_length=512)),
                ('dttm_work_start_plan', models.DateTimeField()),
                ('dttm_work_end_plan', models.DateTimeField()),
                ('dttm_work_start_fact', models.DateTimeField()),
                ('dttm_work_end_fact', models.DateTimeField()),
            ],
            options={
                'db_table': 'timetable_plan_and_fact_hours',
                'managed': False,
            },
        ),
    ]