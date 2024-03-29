# Generated by Django 2.2.7 on 2020-02-05 09:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0008_auto_20200205_0924'),
    ]

    operations = [
        migrations.RunSQL("update base_group set code=null where code=''"),
        migrations.RunSQL("update base_region set code=null where code=''"),
        migrations.RunSQL("update base_workerposition set code=null where code=''"),

        migrations.AlterField(
            model_name='group',
            name='code',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='region',
            name='code',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='workerposition',
            name='code',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
    ]
