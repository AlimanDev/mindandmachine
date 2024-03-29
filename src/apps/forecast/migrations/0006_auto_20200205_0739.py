# Generated by Django 2.2.7 on 2020-02-05 07:39

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forecast', '0005_removefield'),
    ]

    operations = [
        migrations.AlterField(
            model_name='operationtypename',
            name='code',
            field=models.CharField(blank=True, max_length=64, null=True),# unique=True),
        ),
        migrations.AlterField(
            model_name='operationtypename',
            name='name',
            field=models.CharField(max_length=128, unique=True),
        ),
        migrations.AlterUniqueTogether(
            name='operationtype',
            unique_together={('work_type', 'operation_type_name')},
        ),
    ]
