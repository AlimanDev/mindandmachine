# Generated by Django 4.1.7 on 2023-07-03 15:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0132_alter_groupworkerdaypermission_employee_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerday',
            name='dt_not_actual',
            field=models.DateField(blank=True, null=True),
        ),
    ]