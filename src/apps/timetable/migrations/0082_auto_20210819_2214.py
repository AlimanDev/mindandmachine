# Generated by Django 2.2.16 on 2021-08-19 22:14

from django.db import migrations, models
import src.common.mixins.bulk_update_or_create


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0122_auto_20210818_1420'),
        ('timetable', '0081_auto_20210811_1818'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkerDayType',
            fields=[
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(help_text='Первычный ключ', max_length=64, primary_key=True, serialize=False, verbose_name='Код')),
                ('name', models.CharField(max_length=64, verbose_name='Имя')),
                ('short_name', models.CharField(max_length=8, verbose_name='Для отображения в ячейке')),
                ('html_color', models.CharField(max_length=7)),
                ('use_in_plan', models.BooleanField(verbose_name='Используем ли в плане')),
                ('use_in_fact', models.BooleanField(verbose_name='Используем ли в факте')),
                ('excel_load_code', models.CharField(max_length=8, unique=True, verbose_name='Текстовый код для загрузки и выгрузки в график/табель')),
                ('is_dayoff', models.BooleanField(help_text='Если не нерабочий день, то необходимо проставлять время и магазин и можно создавать несколько на 1 дату', verbose_name='Нерабочий день')),
                ('is_work_hours', models.BooleanField(help_text='Если False, то не учитывается в сумме рабочих часов в статистике и не идет в белый табель', verbose_name='Считать ли в сумму рабочих часов')),
                ('is_reduce_norm', models.BooleanField(verbose_name='Снижает ли норму часов (отпуска, больничные и тд)')),
                ('is_system', models.BooleanField(default=False, verbose_name='Системный (нельзя удалять)')),
                ('show_stat_in_days', models.BooleanField(default=True, verbose_name='Отображать в статистике по сотрудникам количество дней отдельно для этого типа')),
                ('show_stat_in_hours', models.BooleanField(default=True, verbose_name='Отображать в статистике по сотрудникам сумму часов отдельно для этого типа')),
                ('ordering', models.PositiveSmallIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['-ordering', 'name'],
                'abstract': False,
            },
            bases=(src.common.mixins.bulk_update_or_create.BatchUpdateOrCreateModelMixin, models.Model),
        ),
    ]
