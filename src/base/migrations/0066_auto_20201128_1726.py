# Generated by Django 2.2.7 on 2020-11-28 17:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0065_auto_20201123_1352'),
    ]

    operations = [
        migrations.AddField(
            model_name='network',
            name='clean_wdays_on_employment_dt_change',
            field=models.BooleanField(default=False, verbose_name='Запускать скрипт очистки дней при изменении дат трудойстройства'),
        ),
    ]