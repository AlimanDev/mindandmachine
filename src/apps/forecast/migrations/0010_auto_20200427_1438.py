# Generated by Django 2.2.7 on 2020-04-27 14:38

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('forecast', '0009_operationtype_shop'),
    ]

    operations = [
        migrations.AlterField(
            model_name='operationtype',
            name='work_type',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='work_type_reversed', to='timetable.WorkType'),
        ),
    ]
