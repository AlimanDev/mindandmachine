# Generated by Django 2.2.7 on 2020-02-06 06:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0005_fix'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cashbox',
            name='code',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
        migrations.AlterField(
            model_name='cashbox',
            name='name',
            field=models.CharField(max_length=128),
        ),
    ]