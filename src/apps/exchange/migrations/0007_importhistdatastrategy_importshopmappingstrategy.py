# Generated by Django 3.2.9 on 2021-11-15 11:37

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exchange', '0006_auto_20211008_0921'),
    ]

    operations = [
        migrations.CreateModel(
            name='ImportHistDataStrategy',
            fields=[
                ('importstrategy_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='exchange.importstrategy')),
                ('system_code', models.CharField(max_length=64, verbose_name='Код системы')),
                ('data_type', models.CharField(max_length=64, verbose_name='Тип данных')),
                ('separated_file_for_each_shop', models.BooleanField(default=False, verbose_name='Отдельный файл для каждого магазина')),
                ('filename_fmt', models.CharField(help_text="Например: '{data_type}_{year:04d}{month:02d}{day:02d}.csv'", max_length=256, verbose_name='Формат файла')),
                ('dt_from', models.CharField(default='today', max_length=32, verbose_name='Дата от')),
                ('dt_to', models.CharField(default='today', max_length=32, verbose_name='Дата до')),
                ('csv_delimiter', models.CharField(default=';', max_length=1, verbose_name='Разделитель csv')),
                ('columns', models.JSONField(blank=True, help_text='Если не указано, то будет использоваться 1 строка как названия колонок', null=True, verbose_name='Наименование колонок в файле')),
                ('shop_num_column_name', models.CharField(max_length=128, verbose_name='Ноименование колонки с номером магазина')),
                ('dt_or_dttm_column_name', models.CharField(max_length=128, verbose_name='Ноименование колонки дата или дата+время')),
                ('dt_or_dttm_format', models.CharField(max_length=128, verbose_name='Формат загрузки колонки дата или дата+время')),
                ('receipt_code_columns', models.JSONField(blank=True, help_text='Если не указано, то в качестве ключа будет использоваться хэш всех колонок', null=True, verbose_name='Колонки, используемые для ключа')),
            ],

            options={
                'verbose_name': 'Стратегия импорта исторических данных',
                'verbose_name_plural': 'Стратегии импорта исторических данных',
            },
            bases=('exchange.importstrategy',),
        ),
        migrations.CreateModel(
            name='ImportShopMappingStrategy',
            fields=[
                ('importstrategy_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='exchange.importstrategy')),
                ('system_code', models.CharField(max_length=64, verbose_name='Код системы')),
                ('system_name', models.CharField(blank=True, max_length=128, null=True, verbose_name='Имя системы')),
                ('filename', models.CharField(max_length=256, verbose_name='Имя файла')),
                ('file_format', models.CharField(choices=[('xlsx', 'Excel (xlsx)'), ('csv', 'Comma-separated values (csv)')], max_length=8, verbose_name='Формат файла', default='xlsx')),
                ('wfm_shop_code_field_name', models.CharField(blank=True, max_length=256, null=True, verbose_name='Название поля кода магазина в WFM-системе')),
                ('wfm_shop_name_field_name', models.CharField(blank=True, max_length=256, null=True, verbose_name='Название поля наименования магазина в WFM-системе')),
                ('external_shop_code_field_name', models.CharField(max_length=256, verbose_name='Название поля кода магазина в внешней системе')),
            ],
            options={
                'verbose_name': 'Стратегия импорт сопоставления кодов магазинов',
                'verbose_name_plural': 'Стратегии импорта сопоставления кодов магазинов',
            },
            bases=('exchange.importstrategy',),
        ),
    ]
