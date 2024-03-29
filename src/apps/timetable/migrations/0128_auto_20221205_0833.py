# Generated by Django 3.2.9 on 2022-12-05 08:33

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('timetable', '0127_merge_0126_auto_20221116_0857_0126_auto_20221118_1206'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='shopmonthstat',
            options={'verbose_name': 'Shop monthly statistics', 'verbose_name_plural': 'Shops monthly statistics'},
        ),
        migrations.AlterField(
            model_name='workerdaytype',
            name='code',
            field=models.CharField(help_text='Primary key', max_length=64, primary_key=True, serialize=False, verbose_name='code'),
        ),
    ]
