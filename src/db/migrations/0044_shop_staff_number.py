# Generated by Django 2.0.5 on 2019-08-09 06:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0043_remove_workerposition_department'),
    ]

    operations = [
        migrations.AddField(
            model_name='shop',
            name='staff_number',
            field=models.SmallIntegerField(default=0),
        ),
    ]