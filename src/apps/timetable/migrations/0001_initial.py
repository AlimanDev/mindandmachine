# Generated by Django 2.2.7 on 2019-12-17 14:58

import datetime
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('base', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Cashbox',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('number', models.PositiveIntegerField(blank=True, null=True)),
                ('bio', models.CharField(blank=True, default='', max_length=512)),
            ],
            options={
                'verbose_name': 'Рабочее место ',
                'verbose_name_plural': 'Рабочие места',
            },
        ),
        migrations.CreateModel(
            name='Event',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('text', models.CharField(max_length=256)),
                ('department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Shop')),
            ],
        ),
        migrations.CreateModel(
            name='ExchangeSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('automatic_check_lack', models.BooleanField(default=False)),
                ('automatic_check_lack_timegap', models.DurationField(default=datetime.timedelta(7))),
                ('automatic_create_vacancy_lack_min', models.FloatField(default=0.5)),
                ('automatic_delete_vacancy_lack_max', models.FloatField(default=0.3)),
                ('automatic_worker_select_timegap', models.DurationField(default=datetime.timedelta(1))),
                ('automatic_worker_select_overflow_min', models.FloatField(default=0.8)),
                ('working_shift_min_hours', models.DurationField(default=datetime.timedelta(0, 14400))),
                ('working_shift_max_hours', models.DurationField(default=datetime.timedelta(0, 43200))),
                ('automatic_worker_select_tree_level', models.IntegerField(default=1)),
                ('automatic_exchange', models.BooleanField(default=False)),
                ('automatic_holiday_worker_select_timegap', models.DurationField(default=datetime.timedelta(8))),
                ('automatic_worker_select_timegap_to', models.DurationField(default=datetime.timedelta(2))),
                ('constraints', models.CharField(default='{"second_day_before": 40, "second_day_after": 32, "first_day_after": 32, "first_day_before": 40, "1day_before": 40, "1day_after": 40}', max_length=250)),
                ('max_working_hours', models.IntegerField(default=192)),
            ],
        ),
        migrations.AddField(
            model_name='exchangesettings',
            name='exclude_positions',
            field=models.ManyToManyField(to='base.WorkerPosition'),
        ),
        migrations.CreateModel(
            name='Slot',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('tm_start', models.TimeField(default=datetime.time(7, 0))),
                ('tm_end', models.TimeField(default=datetime.time(23, 59, 59))),
                ('name', models.CharField(blank=True, max_length=32, null=True)),
                ('workers_needed', models.IntegerField(default=1)),
                ('shop', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='base.Shop')),
            ],
            options={
                'verbose_name': 'Слот',
                'verbose_name_plural': 'Слоты',
            },
        ),
        migrations.CreateModel(
            name='WorkerDay',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dt', models.DateField()),
                ('dttm_work_start', models.DateTimeField(blank=True, null=True)),
                ('dttm_work_end', models.DateTimeField(blank=True, null=True)),
                ('type', models.CharField(choices=[('H', 'Выходной'), ('W', 'Рабочий день'), ('V', 'Отпуск'), ('S', 'Больничный лист'), ('Q', 'Квалификация'), ('A', 'Неявка до выяснения обстоятельств'), ('M', 'Б/л по беременноси и родам'), ('T', 'Командировка'), ('O', 'Другое'), ('D', 'Удален'), ('E', 'Пусто'), ('HW', 'Работа в выходной день'), ('RA', 'Прогул на основании акта'), ('EV', 'Доп. отпуск'), ('SV', 'Учебный отпуск'), ('TV', 'Отпуск за свой счёт'), ('ST', 'Отпуск за свой счёт по уважительной причине'), ('G', 'Гос. обязанности'), ('HS', 'Спец. выходной'), ('MC', 'Отпуск по уходу за ребёнком до 3-х лет'), ('C', 'Выходные дни по уходу')], default='E', max_length=2)),
                ('comment', models.TextField(blank=True, null=True)),
                ('work_hours', models.SmallIntegerField(default=0)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='user_created', to=settings.AUTH_USER_MODEL)),
                ('employment', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Employment')),
                ('parent_worker_day', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='child', to='timetable.WorkerDay')),
                ('shop', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Shop')),
                ('canceled', models.BooleanField(default=False)),
            ],
            options={
                'verbose_name': 'Рабочий день сотрудника',
                'verbose_name_plural': 'Рабочие дни сотрудников',
            },
        ),
        migrations.CreateModel(
            name='WorkType',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('priority', models.PositiveIntegerField(default=100)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('dttm_last_update_queue', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=128)),
                ('min_workers_amount', models.IntegerField(blank=True, default=0, null=True)),
                ('max_workers_amount', models.IntegerField(blank=True, default=20, null=True)),
                ('probability', models.FloatField(default=1.0)),
                ('prior_weight', models.FloatField(default=1.0)),
                ('period_queue_params', models.CharField(default='{"max_depth": 10, "eta": 0.2, "min_split_loss": 1, "reg_lambda": 0.1, "silent": 1, "iterations": 20}', max_length=1024)),
                ('shop', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='base.Shop')),
            ],
            options={
                'verbose_name': 'Тип работ',
                'verbose_name_plural': 'Типы работ',
            },
        ),
        migrations.CreateModel(
            name='WorkerDayCashboxDetails',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('W', 'work period'), ('B', 'rest / break'), ('S', 'study period'), ('V', 'vacancy'), ('Z', 'work in trading floor')], default='W', max_length=1)),
                ('is_vacancy', models.BooleanField(default=False)),
                ('is_tablet', models.BooleanField(default=False)),
                ('dttm_from', models.DateTimeField()),
                ('dttm_to', models.DateTimeField(blank=True, null=True)),
                ('on_cashbox', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='timetable.Cashbox')),
                ('work_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='timetable.WorkType')),
                ('worker_day', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='timetable.WorkerDay')),
                ('work_part', models.FloatField(default=1.0)),
            ],
            options={
                'verbose_name': 'Детали в течение рабочего дня',
            },
        ),
        migrations.CreateModel(
            name='WorkerDayApprove',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dt_approved', models.DateField()),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_deleted', models.DateTimeField(blank=True, null=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ('shop', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='base.Shop')),
            ],
            options={
                'verbose_name': 'Подверждение расписания',
                'verbose_name_plural': 'Подтверждения расписания',
            },
        ),
        migrations.AddField(
            model_name='workerday',
            name='work_types',
            field=models.ManyToManyField(through='timetable.WorkerDayCashboxDetails', to='timetable.WorkType'),
        ),
        migrations.AddField(
            model_name='workerday',
            name='worker',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='workerday',
            name='worker_day_approve',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='timetable.WorkerDayApprove'),
        ),
        migrations.CreateModel(
            name='UserWeekdaySlot',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weekday', models.SmallIntegerField()),
                ('is_suitable', models.BooleanField(default=True)),
                ('employment', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Employment')),
                ('shop', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Shop')),
                ('slot', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='timetable.Slot')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Пользовательский слот',
                'verbose_name_plural': 'Пользовательские слоты',
            },
        ),
        migrations.AddField(
            model_name='slot',
            name='work_type',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='timetable.WorkType'),
        ),
        migrations.AddField(
            model_name='slot',
            name='worker',
            field=models.ManyToManyField(through='timetable.UserWeekdaySlot', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='Notifications',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('was_read', models.BooleanField(default=False)),
                ('event', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='timetable.Event')),
                ('shop', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='notifications', to='base.Shop')),
                ('to_worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Уведомления',
            },
        ),
        migrations.AddField(
            model_name='event',
            name='workerday_details',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='timetable.WorkerDayCashboxDetails'),
        ),
        migrations.AddField(
            model_name='cashbox',
            name='type',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='timetable.WorkType'),
        ),
        migrations.CreateModel(
            name='AttendanceRecords',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm', models.DateTimeField()),
                ('type', models.CharField(choices=[('C', 'coming'), ('L', 'leaving'), ('S', 'break start'), ('E', 'break_end')], max_length=1)),
                ('verified', models.BooleanField(default=True)),
                ('shop', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='base.Shop')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Данные УРВ',
            },
        ),
        migrations.CreateModel(
            name='WorkerDayChangeRequest',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('status_type', models.CharField(choices=[('A', 'Approved'), ('D', 'Declined'), ('P', 'Pending')], default='P', max_length=1)),
                ('dt', models.DateField()),
                ('type', models.CharField(choices=[('H', 'Выходной'), ('W', 'Рабочий день'), ('V', 'Отпуск'), ('S', 'Больничный лист'), ('Q', 'Квалификация'), ('A', 'Неявка до выяснения обстоятельств'), ('M', 'Б/л по беременноси и родам'), ('T', 'Командировка'), ('O', 'Другое'), ('D', 'Удален'), ('E', 'Пусто'), ('HW', 'Работа в выходной день'), ('RA', 'Прогул на основании акта'), ('EV', 'Доп. отпуск'), ('SV', 'Учебный отпуск'), ('TV', 'Отпуск за свой счёт'), ('ST', 'Отпуск за свой счёт по уважительной причине'), ('G', 'Гос. обязанности'), ('HS', 'Спец. выходной'), ('MC', 'Отпуск по уходу за ребёнком до 3-х лет'), ('C', 'Выходные дни по уходу')], default='E', max_length=2)),
                ('dttm_work_start', models.DateTimeField(blank=True, null=True)),
                ('dttm_work_end', models.DateTimeField(blank=True, null=True)),
                ('wish_text', models.CharField(blank=True, max_length=512, null=True)),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Запрос на изменения рабочего дня',
                'unique_together': {('worker', 'dt')},
            },
        ),
        migrations.CreateModel(
            name='WorkerConstraint',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('weekday', models.SmallIntegerField()),
                ('is_lite', models.BooleanField(default=False)),
                ('tm', models.TimeField()),
                ('employment', models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Employment')),
                ('shop', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='worker_constraints', to='base.Shop')),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Ограничения сотрудника',
                'unique_together': {('employment', 'weekday', 'tm')},
            },
        ),
        migrations.CreateModel(
            name='WorkerCashboxInfo',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('is_active', models.BooleanField(default=True)),
                ('period', models.PositiveIntegerField(default=90)),
                ('mean_speed', models.FloatField(default=1)),
                ('bills_amount', models.PositiveIntegerField(default=0)),
                ('priority', models.IntegerField(default=0)),
                ('duration', models.FloatField(default=0)),
                ('employment', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='base.Employment')),
                ('work_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='timetable.WorkType')),
            ],
            options={
                'verbose_name': 'Информация по сотруднику-типу работ',
                'unique_together': {('employment', 'work_type')},
            },
        ),
        migrations.CreateModel(
            name='Timetable',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('status_message', models.CharField(blank=True, max_length=256, null=True)),
                ('dt', models.DateField()),
                ('status', models.CharField(choices=[('R', 'Готово'), ('P', 'В процессе'), ('E', 'Ошибка')], default='P', max_length=1)),
                ('dttm_status_change', models.DateTimeField()),
                ('fot', models.IntegerField(blank=True, default=0, null=True)),
                ('lack', models.SmallIntegerField(blank=True, default=0, null=True)),
                ('idle', models.SmallIntegerField(blank=True, default=0, null=True)),
                ('workers_amount', models.IntegerField(blank=True, default=0, null=True)),
                ('revenue', models.IntegerField(blank=True, default=0, null=True)),
                ('fot_revenue', models.IntegerField(blank=True, default=0, null=True)),
                ('task_id', models.CharField(blank=True, max_length=256, null=True)),
                ('shop', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='timetable', to='base.Shop')),
            ],
            options={
                'verbose_name': 'Расписание',
                'verbose_name_plural': 'Расписания',
                'unique_together': {('shop', 'dt')},
            },
        ),
        migrations.AlterUniqueTogether(
            name='workerconstraint',
            unique_together={('employment', 'weekday', 'tm')},
        ),
    ]