# Generated by Django 2.0.5 on 2018-07-10 08:35

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0030_auto_20180625_1458'),
    ]

    operations = [
        migrations.AddField(
            model_name='cashbox',
            name='is_busy',
            field=models.BooleanField(default=False),
        ),
    ]
