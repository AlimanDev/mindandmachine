# Generated by Django 2.0.5 on 2018-05-04 11:34

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0007_slot'),
    ]

    operations = [
        migrations.RenameField(
            model_name='workerposition',
            old_name='position',
            new_name='title',
        ),
    ]
