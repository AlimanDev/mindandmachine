# Generated by Django 2.2.7 on 2020-10-19 18:44

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0036_auto_20201008_0850'),
    ]

    operations = [
        migrations.AddField(
            model_name='shopmonthstat',
            name='predict_needs',
            field=models.IntegerField(blank=True, default=0, null=True, verbose_name='Количество часов по нагрузке'),
        ),
    ]
