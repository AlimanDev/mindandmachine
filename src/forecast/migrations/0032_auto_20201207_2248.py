# Generated by Django 2.2.7 on 2020-12-07 22:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forecast', '0031_auto_20201127_1315'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='receipt',
            options={'verbose_name': 'Событийные данные', 'verbose_name_plural': 'Событийные данные'},
        ),
        migrations.AlterField(
            model_name='operationtypename',
            name='code',
            field=models.CharField(blank=True, max_length=64, null=True, verbose_name='Код'),
        ),
        migrations.AlterField(
            model_name='operationtypename',
            name='name',
            field=models.CharField(max_length=128, verbose_name='Имя'),
        ),
    ]