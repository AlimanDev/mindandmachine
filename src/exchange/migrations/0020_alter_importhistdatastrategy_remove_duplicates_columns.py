# Generated by Django 3.2.9 on 2022-12-19 10:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exchange', '0019_auto_20221219_1021'),
    ]

    operations = [
        migrations.AlterField(
            model_name='importhistdatastrategy',
            name='remove_duplicates_columns',
            field=models.JSONField(blank=True, null=True, verbose_name='take this'),
        ),
    ]