# Generated by Django 2.2.16 on 2021-05-03 18:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0066_auto_20210430_1222'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workerday',
            name='is_outsource',
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]