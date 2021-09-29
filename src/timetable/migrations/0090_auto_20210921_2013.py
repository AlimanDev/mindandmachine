# Generated by Django 2.2.16 on 2021-09-21 20:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0089_auto_20210908_1612'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workerdaypermission',
            name='action',
            field=models.CharField(choices=[('CU', 'Создание/изменение'), ('D', 'Удаление'), ('A', 'Подтверждение')], max_length=2, verbose_name='Действие'),
        ),
    ]
