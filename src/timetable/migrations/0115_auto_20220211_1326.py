# Generated by Django 3.2.9 on 2022-02-11 13:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0114_auto_20220207_1053'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='event',
            name='department',
        ),
        migrations.RemoveField(
            model_name='event',
            name='workerday_details',
        ),
        migrations.RemoveField(
            model_name='notifications',
            name='event',
        ),
        migrations.RemoveField(
            model_name='notifications',
            name='shop',
        ),
        migrations.RemoveField(
            model_name='notifications',
            name='to_worker',
        ),
        migrations.AlterUniqueTogether(
            name='workerdaychangerequest',
            unique_together=None,
        ),
        migrations.RemoveField(
            model_name='workerdaychangerequest',
            name='worker',
        ),
        migrations.AlterField(
            model_name='groupworkerdaypermission',
            name='allow_actions_on_vacancies',
            field=models.BooleanField(default=True, help_text='Вакансией в данном случае является день, если он был явно создан как вакансия, либо если магазин в трудоустройстве не совпадает с магазином выхода (актуально для рабочий типов дней)', verbose_name='Allow actions on vacancies'),
        ),
        migrations.AlterField(
            model_name='groupworkerdaypermission',
            name='employee_type',
            field=models.PositiveSmallIntegerField(choices=[(1, 'My shops employees'), (2, 'Subordinate employees'), (3, 'Outsource network employees'), (4, 'My network employees')], default=2, verbose_name='Тип сотрудника'),
        ),
        migrations.AlterField(
            model_name='groupworkerdaypermission',
            name='shop_type',
            field=models.PositiveSmallIntegerField(choices=[(1, 'My shops'), (2, 'My network shops'), (3, 'Outsource network shops'), (4, 'Client network shops')], default=2, help_text='Актуально только для рабочих типов дней', verbose_name='Тип магазина'),
        ),
        migrations.AlterField(
            model_name='workerdaypermission',
            name='graph_type',
            field=models.CharField(choices=[('P', 'Plan'), ('F', 'Fact')], max_length=1, verbose_name='Тип графика'),
        ),
        migrations.DeleteModel(
            name='Cashbox',
        ),
        migrations.DeleteModel(
            name='Event',
        ),
        migrations.DeleteModel(
            name='Notifications',
        ),
        migrations.DeleteModel(
            name='WorkerDayChangeRequest',
        ),
    ]
