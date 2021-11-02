# Generated by Django 2.2.16 on 2021-08-10 15:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0119_auto_20210805_1711'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='allow_creation_several_wdays_for_one_employee_for_one_date',
            field=models.BooleanField(default=False, verbose_name='Разрешить создание нескольких рабочих дней для 1 сотрудника на 1 дату'),
        ),
        migrations.AddField(
            model_name='network',
            name='consider_department_in_att_records',
            field=models.BooleanField(default=False, verbose_name='Учитывать отдел при поиске плана при совершении отметки и при пересчете факта на основе отметок'),
        ),
        migrations.AddField(
            model_name='network',
            name='run_recalc_fact_from_att_records_on_plan_approve',
            field=models.BooleanField(default=False, verbose_name='Запускать пересчет факта на основе отметок при подтверждении плана'),
        ),
        migrations.AddField(
            model_name='network',
            name='set_closest_plan_approved_delta_for_manual_fact',
            field=models.PositiveIntegerField(default=18000, verbose_name='Макс. разница времени начала и времени окончания в факте и в плане при проставлении ближайшего плана в ручной факт (в секундах)'),
        ),
    ]
