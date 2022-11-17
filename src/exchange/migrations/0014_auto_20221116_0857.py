# Generated by Django 3.2.9 on 2022-11-16 08:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exchange', '0013_alter_localfilesystemconnector_default_base_path'),
    ]

    operations = [
        migrations.AddField(
            model_name='importhistdatastrategy',
            name='fix_date',
            field=models.BooleanField(default=False, verbose_name='Нужно ли заменять дату внутри файла на ту, что в имени'),
        ),
        migrations.AlterField(
            model_name='localfilesystemconnector',
            name='default_base_path',
            field=models.CharField(default='/webapp', max_length=512),
        ),
    ]
