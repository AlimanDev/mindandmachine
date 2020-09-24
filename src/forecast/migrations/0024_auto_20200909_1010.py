# Generated by Django 2.2.7 on 2020-09-09 10:10

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0032_auto_20200904_0447'),
        ('forecast', '0023_merge_20200907_0831'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='operationtype',
            name='do_forecast',
        ),
        migrations.RemoveField(
            model_name='operationtypetemplate',
            name='do_forecast',
        ),
        migrations.RemoveField(
            model_name='operationtypetemplate',
            name='work_type_name',
        ),
        migrations.AddField(
            model_name='operationtypename',
            name='do_forecast',
            field=models.CharField(choices=[('H', 'Forecast'), ('F', 'Formula')], default='H', max_length=1),
        ),
        migrations.AddField(
            model_name='operationtypename',
            name='work_type_name',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='timetable.WorkTypeName'),
        ),
    ]
