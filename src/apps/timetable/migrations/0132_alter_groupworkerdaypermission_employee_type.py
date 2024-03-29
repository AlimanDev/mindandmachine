# Generated by Django 3.2.9 on 2023-02-13 15:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0131_merge_20230112_1544'),
    ]

    operations = [
        migrations.AlterField(
            model_name='groupworkerdaypermission',
            name='employee_type',
            field=models.PositiveSmallIntegerField(choices=[(1, 'My shops employees'), (2, 'Subordinate employees'), (3, 'Other shop or network employees'), (4, 'My network employees')], default=2, verbose_name='Тип сотрудника'),
        ),
    ]
