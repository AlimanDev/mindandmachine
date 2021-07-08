# Generated by Django 2.2.16 on 2021-07-07 07:35

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0113_auto_20210706_0939'),
        ('timetable', '0074_merge_20210604_1116'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='exchangesettings',
            name='automatic_check_lack',
        ),
        migrations.AddField(
            model_name='exchangesettings',
            name='automatic_create_vacancies',
            field=models.BooleanField(default=False, verbose_name='Automatic create vacancies'),
        ),
        migrations.AddField(
            model_name='exchangesettings',
            name='automatic_delete_vacancies',
            field=models.BooleanField(default=False, verbose_name='Automatic delete vacancies'),
        ),
        migrations.AddField(
            model_name='exchangesettings',
            name='outsources',
            field=models.ManyToManyField(blank=True, help_text='Outsourcing companies that will be able to respond to an automatically created vacancy', related_name='client_exchange_settings', to='base.Network', verbose_name='Outsourcing companies'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='automatic_check_lack_timegap',
            field=models.DurationField(default=datetime.timedelta(7), verbose_name='Automatic check lack timegap'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='automatic_create_vacancy_lack_min',
            field=models.FloatField(default=0.5, verbose_name='Automatic create vacancy lack min'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='automatic_delete_vacancy_lack_max',
            field=models.FloatField(default=0.3, verbose_name='Automatic delete vacancy lack max'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='automatic_exchange',
            field=models.BooleanField(default=False, verbose_name='Automatic exchange'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='automatic_holiday_worker_select_timegap',
            field=models.DurationField(default=datetime.timedelta(8), verbose_name='Automatic holiday worker select timegap'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='automatic_worker_select_overflow_min',
            field=models.FloatField(default=0.8, verbose_name='Automatic worker select overflow min'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='automatic_worker_select_timegap',
            field=models.DurationField(default=datetime.timedelta(1), verbose_name='Automatic worker select timegap'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='automatic_worker_select_timegap_to',
            field=models.DurationField(default=datetime.timedelta(2), verbose_name='Automatic worker select timegap to'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='automatic_worker_select_tree_level',
            field=models.IntegerField(default=1, verbose_name='Automatic worker select tree level'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='constraints',
            field=models.CharField(default='{"second_day_before": 40, "second_day_after": 32, "first_day_after": 32, "first_day_before": 40, "1day_before": 40, "1day_after": 40}', max_length=250, verbose_name='Constraints'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='exclude_positions',
            field=models.ManyToManyField(blank=True, to='base.WorkerPosition', verbose_name='Exclude positions'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='max_working_hours',
            field=models.IntegerField(default=192, verbose_name='Max working hours'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='working_shift_max_hours',
            field=models.DurationField(default=datetime.timedelta(0, 43200), verbose_name='Working shift max hours'),
        ),
        migrations.AlterField(
            model_name='exchangesettings',
            name='working_shift_min_hours',
            field=models.DurationField(default=datetime.timedelta(0, 14400), verbose_name='Working shift min hours'),
        ),
    ]
