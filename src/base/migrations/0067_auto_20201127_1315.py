# Generated by Django 2.2.7 on 2020-11-27 13:15

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0066_network_crop_work_hours_by_shop_schedule'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='break',
            options={'ordering': ['name'], 'verbose_name': 'Перерыв', 'verbose_name_plural': 'Перерывы'},
        ),
        migrations.AlterModelOptions(
            name='group',
            options={'ordering': ['name'], 'verbose_name': 'Группа пользователей', 'verbose_name_plural': 'Группы пользователей'},
        ),
        migrations.AlterModelOptions(
            name='region',
            options={'ordering': ['name'], 'verbose_name': 'Регион', 'verbose_name_plural': 'Регионы'},
        ),
        migrations.AlterModelOptions(
            name='shopsettings',
            options={'ordering': ['name'], 'verbose_name': 'Настройки автосоставления', 'verbose_name_plural': 'Настройки автосоставления'},
        ),
        migrations.AlterModelOptions(
            name='workerposition',
            options={'ordering': ['name'], 'verbose_name': 'Должность сотрудника', 'verbose_name_plural': 'Должности сотрудников'},
        ),
    ]
