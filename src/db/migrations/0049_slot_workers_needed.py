# Generated by Django 2.0.5 on 2018-08-29 09:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0048_merge_20180820_1453'),
    ]

    operations = [
        migrations.AddField(
            model_name='slot',
            name='workers_needed',
            field=models.IntegerField(default=1),
        ),
    ]