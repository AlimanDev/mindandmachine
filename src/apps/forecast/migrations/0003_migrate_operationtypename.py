# Generated by Django 2.2.7 on 2019-12-23 10:19

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('forecast', '0002_auto_20191223_1019'),
    ]

    operations = [
        migrations.AddField(
            model_name='operationtype',
            name='operation_type_name',
            field=models.ForeignKey(default=1, on_delete=django.db.models.deletion.PROTECT, to='forecast.OperationTypeName'),
            preserve_default=False,
        ),
    ]
