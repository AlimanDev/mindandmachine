# Generated by Django 3.2.9 on 2022-02-07 10:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0113_merge_0112_auto_20220112_1801_0112_auto_20220203_1319'),
    ]

    operations = [
        migrations.CreateModel(
            name='ScheduleDeviations',
            fields=[
                ('id', models.CharField(max_length=256, primary_key=True, serialize=False)),
                ('dt', models.DateField()),
                ('shop_name', models.CharField(max_length=512)),
                ('shop_code', models.CharField(max_length=512)),
                ('tabel_code', models.CharField(max_length=64)),
                ('worker_fio', models.CharField(max_length=512)),
                ('fact_work_hours', models.DecimalField(decimal_places=2, max_digits=4)),
                ('plan_work_hours', models.DecimalField(decimal_places=2, max_digits=4)),
                ('fact_manual_work_hours', models.DecimalField(decimal_places=2, max_digits=4)),
                ('late_arrival_hours', models.DecimalField(decimal_places=2, max_digits=4)),
                ('early_departure_hours', models.DecimalField(decimal_places=2, max_digits=4)),
                ('early_arrival_hours', models.DecimalField(decimal_places=2, max_digits=4)),
                ('late_departure_hours', models.DecimalField(decimal_places=2, max_digits=4)),
                ('fact_without_plan_work_hours', models.DecimalField(decimal_places=2, max_digits=4)),
                ('lost_work_hours', models.DecimalField(decimal_places=2, max_digits=4)),
                ('late_arrival_count', models.PositiveSmallIntegerField()),
                ('early_departure_count', models.PositiveSmallIntegerField()),
                ('early_arrival_count', models.PositiveSmallIntegerField()),
                ('late_departure_count', models.PositiveSmallIntegerField()),
                ('fact_without_plan_count', models.PositiveSmallIntegerField()),
                ('lost_work_hours_count', models.PositiveSmallIntegerField()),
                ('is_vacancy', models.BooleanField()),
                ('ticks_fact_count', models.PositiveSmallIntegerField()),
                ('ticks_plan_count', models.PositiveSmallIntegerField()),
                ('ticks_comming_fact_count', models.PositiveSmallIntegerField()),
                ('ticks_leaving_fact_count', models.PositiveSmallIntegerField()),
                ('worker_username', models.CharField(max_length=512)),
                ('work_type_name', models.CharField(max_length=512)),
                ('dttm_work_start_plan', models.DateTimeField()),
                ('dttm_work_end_plan', models.DateTimeField()),
                ('dttm_work_start_fact', models.DateTimeField()),
                ('dttm_work_end_fact', models.DateTimeField()),
                ('is_outsource', models.BooleanField()),
                ('user_network', models.CharField(max_length=512)),
                ('employment_shop_name', models.CharField(max_length=512)),
                ('position_name', models.CharField(max_length=512)),
            ],
            options={
                'db_table': 'timetable_schedule_deviations',
                'managed': False,
            },
        ),
        migrations.AlterField(
            model_name='groupworkerdaypermission',
            name='employee_type',
            field=models.PositiveSmallIntegerField(choices=[(1, 'Любые сотрудники моих магазинов'), (2, 'Подчиненные сотрудники'), (3, 'Сотрудники аутсорс компании'), (4, 'Любые сотрудники моей сети')], default=2, verbose_name='Тип сотрудника'),
        ),
        migrations.AlterField(
            model_name='groupworkerdaypermission',
            name='shop_type',
            field=models.PositiveSmallIntegerField(choices=[(1, 'Мои магазины'), (2, 'Любые магазины моей сети'), (3, 'Магазины аутсорс сетей'), (4, 'Магазины сети аутсорс-клиента')], default=2, help_text='Актуально только для рабочих типов дней', verbose_name='Тип магазина'),
        ),
        migrations.AlterField(
            model_name='workerdaypermission',
            name='action',
            field=models.CharField(choices=[('C', 'Create'), ('U', 'Change'), ('D', 'Remove'), ('A', 'Approve')], max_length=4, verbose_name='Действие'),
        ),
    ]
