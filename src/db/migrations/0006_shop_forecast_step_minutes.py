# Generated by Django 2.0.5 on 2018-05-04 09:35

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0005_auto_20180504_0927'),
    ]

    operations = [
        migrations.AddField(
            model_name='shop',
            name='forecast_step_minutes',
            field=models.TimeField(default=datetime.time(0, 15)),
        ),
    ]
