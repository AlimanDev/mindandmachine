# Generated by Django 3.2.9 on 2022-12-23 16:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0129_merge_0128_auto_20221205_0833_0128_auto_20221205_1331'),
    ]

    operations = [
        migrations.AlterField(
            model_name='workerday',
            name='code',
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
    ]
