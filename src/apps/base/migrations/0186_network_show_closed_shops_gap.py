# Generated by Django 3.2.9 on 2022-10-18 14:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0185_auto_20221012_1108'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='show_closed_shops_gap',
            field=models.PositiveIntegerField(default=30, verbose_name='Show closed shops in shop tree for N days'),
        ),
    ]
