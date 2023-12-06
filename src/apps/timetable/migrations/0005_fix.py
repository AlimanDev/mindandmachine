# Generated by Django 2.2.7 on 2020-02-05 09:24

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0005_auto_20200205_0924'),
    ]

    operations = [

        migrations.RunSQL("update timetable_cashbox set code=null where code=''"),
        migrations.RunSQL("update timetable_slot set code=null where code=''"),
        migrations.AlterField(
            model_name='cashbox',
            name='code',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='slot',
            name='code',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
    ]