# Generated by Django 2.2.24 on 2021-09-27 22:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forecast', '0042_auto_20210927_2057'),
    ]

    operations = [
        migrations.AlterField(
            model_name='receipt',
            name='code',
            field=models.CharField(db_index=True, max_length=256),
        ),
    ]
