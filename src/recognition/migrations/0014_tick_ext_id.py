# Generated by Django 2.2.3 on 2019-08-07 12:34

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '__first__'),
        ('recognition', '0013_auto_20190806_1210'),
    ]

    operations = [
        migrations.AddField(
            model_name='tick',
            name='ext_id',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='timetable.AttendanceRecords'),
        ),
    ]
