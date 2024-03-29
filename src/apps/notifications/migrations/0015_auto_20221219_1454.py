# Generated by Django 3.2.9 on 2022-12-19 14:54

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0014_auto_20221219_1448'),
    ]

    operations = [
        migrations.AlterField(
            model_name='eventemailnotification',
            name='shop_ancestors_level',
            field=models.PositiveIntegerField(blank=True, default=None, help_text='Leave blank for all', null=True, verbose_name='Ancestor level'),
        ),
        migrations.AlterField(
            model_name='eventonlinenotification',
            name='shop_ancestors_level',
            field=models.PositiveIntegerField(blank=True, default=None, help_text='Leave blank for all', null=True, verbose_name='Ancestor level'),
        ),
    ]
