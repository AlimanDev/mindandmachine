# Generated by Django 2.2.7 on 2020-09-24 15:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0032_auto_20200904_0447'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopmonthstat',
            name='is_approved',
            field=models.BooleanField(default=False),
        ),
    ]
