# Generated by Django 3.2.9 on 2022-12-20 14:02

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0016_auto_20221219_1647'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='eventemailnotification',
            name='shop_ancestors_level',
        ),
        migrations.RemoveField(
            model_name='eventonlinenotification',
            name='shop_ancestors_level',
        ),
        migrations.AddField(
            model_name='eventemailnotification',
            name='shop_parent',
            field=models.BooleanField(default=False, verbose_name='Parent shop'),
        ),
        migrations.AddField(
            model_name='eventonlinenotification',
            name='shop_parent',
            field=models.BooleanField(default=False, verbose_name='Parent shop'),
        ),
    ]
