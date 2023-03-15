# Generated by Django 4.1.7 on 2023-03-09 15:52

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0193_merge_20230118_1255'),
    ]

    operations = [
        migrations.AlterField(
            model_name='network',
            name='forbid_edit_work_days_came_through_integration',
            field=models.BooleanField(blank=True, default=False, null=True, verbose_name='Forbid editing work days which came from integration'),
        ),
        migrations.AlterField(
            model_name='shop',
            name='exchange_shops',
            field=models.ManyToManyField(blank=True, to='base.shop'),
        ),
    ]
