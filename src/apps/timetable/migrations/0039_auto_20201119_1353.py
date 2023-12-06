# Generated by Django 2.2.7 on 2020-11-19 13:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0038_groupworkerdaypermission_workerdaypermission'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workerdaypermission',
            name='wd_type',
            field=models.CharField(choices=[('H', 'Выходной'), ('W', 'Рабочий день'), ('V', 'Отпуск'), ('S', 'Больничный лист'), ('Q', 'Квалификация'), ('A', 'Неявка до выяснения обстоятельств'), ('M', 'Б/л по беременноси и родам'), ('T', 'Командировка'), ('O', 'Другое'), ('D', 'Удален'), ('E', 'Пусто'), ('HW', 'Работа в выходной день'), ('RA', 'Прогул на основании акта'), ('EV', 'Доп. отпуск'), ('SV', 'Учебный отпуск'), ('TV', 'Отпуск за свой счёт'), ('ST', 'Отпуск за свой счёт по уважительной причине'), ('G', 'Гос. обязанности'), ('HS', 'Спец. выходной'), ('MC', 'Отпуск по уходу за ребёнком до 3-х лет'), ('C', 'Выходные дни по уходу')], max_length=2, verbose_name='Тип дня'),
        ),
    ]