# Generated by Django 2.2.24 on 2021-09-23 18:18

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='BaseFilesystemConnector',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=256)),
                ('polymorphic_ctype', models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='polymorphic_exchange.basefilesystemconnector_set+', to='contenttypes.ContentType')),
            ],
            options={
                'verbose_name': 'Коннектор к файловой системы',
                'verbose_name_plural': 'Коннекторы к файловой системе',
            },
        ),
        migrations.CreateModel(
            name='ExportStrategy',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=256)),
                ('polymorphic_ctype', models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='polymorphic_exchange.exportstrategy_set+', to='contenttypes.ContentType')),
            ],
            options={
                'verbose_name': 'Стратегия экспорта',
                'verbose_name_plural': 'Стратегии экспорта',
            },
        ),
        migrations.CreateModel(
            name='ImportStrategy',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=256)),
                ('polymorphic_ctype', models.ForeignKey(editable=False, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='polymorphic_exchange.importstrategy_set+', to='contenttypes.ContentType')),
            ],
            options={
                'verbose_name': 'Стратегия импорта',
                'verbose_name_plural': 'Стратегии импорта',
            },
        ),
        migrations.CreateModel(
            name='FtpFilesystemConnector',
            fields=[
                ('basefilesystemconnector_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='exchange.BaseFilesystemConnector')),
                ('base_path', models.CharField(max_length=512)),
                ('host', models.CharField(max_length=128)),
                ('port', models.PositiveSmallIntegerField(default=21)),
                ('username', models.CharField(max_length=128)),
                ('password', models.CharField(max_length=50)),
            ],
            options={
                'verbose_name': 'Коннектор к FTP',
                'verbose_name_plural': 'Коннекторы к FTP',
            },
            bases=('exchange.basefilesystemconnector',),
        ),
        migrations.CreateModel(
            name='LocalFilesystemConnector',
            fields=[
                ('basefilesystemconnector_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='exchange.BaseFilesystemConnector')),
                ('base_path', models.CharField(default='/home/wonder/PycharmProjects/QoS_backend', max_length=512)),
            ],
            options={
                'verbose_name': 'Коннектор к локальной файловой системе',
                'verbose_name_plural': 'Коннекторы к локальной файловой системе',
            },
            bases=('exchange.basefilesystemconnector',),
        ),
        migrations.CreateModel(
            name='SystemExportStrategy',
            fields=[
                ('exportstrategy_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='exchange.ExportStrategy')),
                ('settings_json', models.TextField(default='{}')),
                ('strategy_type', models.CharField(choices=[('work_hours_pivot_table', 'Сводная таблица по отработанным часам по всем магазинам')], max_length=128)),
            ],
            options={
                'verbose_name': 'Системная стратегия экспорта',
                'verbose_name_plural': 'Системные стратегии экспорта',
            },
            bases=('exchange.exportstrategy',),
        ),
        migrations.CreateModel(
            name='SystemImportStrategy',
            fields=[
                ('importstrategy_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='exchange.ImportStrategy')),
                ('settings_json', models.TextField(default='{}')),
                ('strategy_type', models.CharField(choices=[('pobeda_import_shop_mapping', 'Импорт сопоставления кодов магазинов (Победа)'), ('pobeda_import_purchases', 'Импорт чеков (Победа)'), ('pobeda_import_deliveries', 'Импорт поставок (Победа)'), ('pobeda_import_day_ahead_deliveries', 'Импорт поставок на день вперед (Победа)'), ('pobeda_import_reassessment', 'Импорт переоценок (Победа)'), ('pobeda_import_write_offs', 'Импорт списаний (Победа)')], max_length=128)),
            ],
            options={
                'verbose_name': 'Системная стратегия импорта',
                'verbose_name_plural': 'Системные стратегии импорта',
            },
            bases=('exchange.importstrategy',),
        ),
        migrations.CreateModel(
            name='ImportJob',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('fs_connector', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='exchange.BaseFilesystemConnector')),
                ('import_strategy', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='exchange.ImportStrategy')),
            ],
            options={
                'verbose_name': 'Задача импорта данных',
                'verbose_name_plural': 'Задачи импорта данных',
            },
        ),
        migrations.CreateModel(
            name='ExportJob',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_modified', models.DateTimeField(auto_now=True)),
                ('export_strategy', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='exchange.ExportStrategy')),
                ('fs_connector', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='exchange.BaseFilesystemConnector')),
            ],
            options={
                'verbose_name': 'Задача экспорта данных',
                'verbose_name_plural': 'Задачи экспорта данных',
            },
        ),
    ]
