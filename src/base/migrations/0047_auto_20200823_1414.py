# Generated by Django 2.2.7 on 2020-08-23 14:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0046_merge_20200810_0713'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='type',
            field=models.CharField(choices=[('vacancy', 'Вакансия'), ('timetable', 'Изменения в расписании'), ('load_template_err', 'Ошибка применения шаблона нагрузки'), ('load_template_apply', 'Шаблон нагрузки применён'), ('shift_elongation', 'Расширение смены'), ('holiday_exchange', 'Вывод с выходного'), ('auto_vacancy', 'Автоматическая биржа смен'), ('vacancy_canceled', 'Вакансия отменена')], max_length=20),
        ),
        migrations.AlterField(
            model_name='subscribe',
            name='type',
            field=models.CharField(choices=[('vacancy', 'Вакансия'), ('timetable', 'Изменения в расписании'), ('load_template_err', 'Ошибка применения шаблона нагрузки'), ('load_template_apply', 'Шаблон нагрузки применён'), ('shift_elongation', 'Расширение смены'), ('holiday_exchange', 'Вывод с выходного'), ('auto_vacancy', 'Автоматическая биржа смен'), ('vacancy_canceled', 'Вакансия отменена')], max_length=20),
        ),
    ]
