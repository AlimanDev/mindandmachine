# Generated by Django 2.0.5 on 2018-07-31 11:32

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0038_auto_20180730_1100'),
    ]

    operations = [
        migrations.AddField(
            model_name='shop',
            name='count_lack',
            field=models.BooleanField(default=False),
        ),
    ]
