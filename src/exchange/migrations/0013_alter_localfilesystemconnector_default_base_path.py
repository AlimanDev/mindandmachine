# Generated by Django 3.2.9 on 2022-10-03 12:08

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exchange', '0012_auto_20220926_1052'),
    ]

    operations = [
        migrations.AlterField(
            model_name='localfilesystemconnector',
            name='default_base_path',
            field=models.CharField(default='/home/victor/projects/QoS_backend', max_length=512),
        ),
    ]