# Generated by Django 3.2.9 on 2022-09-26 18:56

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0123_auto_20220919_0932'),
    ]

    operations = [
        migrations.AlterField(
            model_name='restriction',
            name='is_vacancy',
            field=models.BooleanField(default=None, null=True, verbose_name='None -- для любой смены (осн. или доп.), True -- только для доп. смен, False -- только для осн. смен'),
        ),
    ]