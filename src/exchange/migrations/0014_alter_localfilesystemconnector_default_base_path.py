# Generated by Django 3.2.9 on 2022-11-18 11:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exchange', '0013_alter_localfilesystemconnector_default_base_path'),
    ]

    operations = [
        migrations.AlterField(
            model_name='localfilesystemconnector',
            name='default_base_path',
            field=models.CharField(default=None, max_length=512, null=True),
        ),
    ]