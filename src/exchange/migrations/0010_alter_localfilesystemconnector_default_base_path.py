# Generated by Django 3.2.9 on 2022-02-11 13:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exchange', '0009_delete_systemimportstrategy'),
    ]

    operations = [
        migrations.AlterField(
            model_name='localfilesystemconnector',
            name='default_base_path',
            field=models.CharField(default='/Users/anton/QoS_backend', max_length=512),
        ),
    ]
