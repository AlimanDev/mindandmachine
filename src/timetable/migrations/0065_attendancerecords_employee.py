# Generated by Django 2.2.16 on 2021-04-27 06:19

from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Subquery, OuterRef

def fill_employee(apps, schema_editor):
    AttendanceRecords = apps.get_model('timetable', 'AttendanceRecords')
    Employee = apps.get_model('base', 'Employee')

    AttendanceRecords.objects.update(
        employee=Subquery(
            Employee.objects.filter(
                user_id=OuterRef('user_id'),
            ).values('id')[:1],
        )
    )


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0096_auto_20210426_1448'),
        ('timetable', '0064_remove_workerconstraint_worker'),
    ]

    operations = [
        migrations.AddField(
            model_name='attendancerecords',
            name='employee',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='base.Employee'),
        ),
        migrations.RunPython(fill_employee),
    ]