# Generated by Django 2.2.16 on 2021-08-11 18:18

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0080_remove_workerday_outsources'),
        ('integration', '0005_auto_20210609_1900'),
    ]

    operations = [
        migrations.RenameField(
            model_name='workerday',
            old_name='allowed_outsource_networks',
            new_name='outsources',
        ),
    ]