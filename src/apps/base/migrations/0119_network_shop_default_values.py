# Generated by Django 2.2.16 on 2021-08-25 19:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0118_merge_20210825_1906'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='shop_default_values',
            field=models.TextField(default='{}', verbose_name='Shop default values'),
        ),
    ]