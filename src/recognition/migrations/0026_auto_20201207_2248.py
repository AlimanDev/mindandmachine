# Generated by Django 2.2.7 on 2020-12-07 22:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recognition', '0025_auto_20201126_0835'),
    ]

    operations = [
        migrations.AlterField(
            model_name='tickpoint',
            name='code',
            field=models.CharField(blank=True, max_length=64, null=True, verbose_name='Код'),
        ),
        migrations.AlterField(
            model_name='tickpoint',
            name='name',
            field=models.CharField(max_length=128, verbose_name='Имя'),
        ),
    ]