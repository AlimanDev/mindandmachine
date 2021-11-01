# Generated by Django 2.2.24 on 2021-09-30 15:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0090_auto_20210921_2013'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workerdaypermission',
            name='action',
            field=models.CharField(choices=[('CU', 'Create/update'), ('D', 'Remove'), ('A', 'Approve')], max_length=2, verbose_name='Действие'),
        ),
    ]