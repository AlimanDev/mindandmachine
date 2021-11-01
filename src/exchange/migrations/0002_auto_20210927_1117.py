# Generated by Django 2.2.24 on 2021-09-27 11:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exchange', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='localfilesystemconnector',
            old_name='base_path',
            new_name='default_base_path',
        ),
        migrations.AddField(
            model_name='exportjob',
            name='base_path',
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AddField(
            model_name='importjob',
            name='base_path',
            field=models.CharField(blank=True, max_length=512),
        ),
    ]