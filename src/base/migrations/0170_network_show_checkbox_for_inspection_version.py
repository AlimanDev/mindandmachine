# Generated by Django 3.2.9 on 2022-06-16 22:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0169_auto_20220214_1146'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='show_checkbox_for_inspection_version',
            field=models.BooleanField(default=True, verbose_name='Show checkbox for downloading inspection version of timetable'),
        ),
    ]
